import discord
import random
import httpx
from discord.ext import commands
from database import SessionLocal, Personagem, Magia
from permissions import require_mestre
from xp_system import aplicar_xp_personagem, cr_para_xp, multiplicador_grupo_monstros
from magia_combate import (
    MAGIA_ESPECIAL,
    normalizar_index_magia,
    dano_guardioes_por_slot,
    rolar_string_dado,
    dc_conjuracao_generico,
    rolar_teste_resistencia,
)
from cogs._combat_helpers import (
    calc_mod as core_calc_mod,
    clean_name,
    extract_monster_spells,
    find_active_monster,
    get_save_modifier,
    has_initiative_advantage,
    roll_d20,
    roll_spell_damage,
    spell_fallback,
)

class CombateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monstros_ativos = []
        self.ordem_combate = []
        self.monstros_killed = []
        self._xp_awarded_vitoria = False
        self.auras = []
        self.aliados = []

    def calc_mod(self, valor):
        return core_calc_mod(valor)

    def _rolar_d20(self, vantagem: bool = False, desvantagem: bool = False):
        return roll_d20(vantagem=vantagem, desvantagem=desvantagem)

    def _vantagem_iniciativa(self, p) -> bool:
        return has_initiative_advantage(p)

    def _achar_monstro_ativo(self, nome_instancia: str):
        return find_active_monster(self.monstros_ativos, nome_instancia)

    async def _carregar_ficha_monstro(self, slug: str):
        url = f"https://www.dnd5eapi.co/api/2014/monsters/{slug}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.json()

    def _extrair_magias_monstro(self, dados_monstro):
        return extract_monster_spells(dados_monstro)

    async def _carregar_spell(self, slug_spell: str):
        url = f"https://www.dnd5eapi.co/api/spells/{slug_spell}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.json()

    def _rolar_dano_spell(self, spell_data):
        return roll_spell_damage(spell_data, rolar_string_dado)

    def _mod_save_personagem(self, p, ability: str):
        return get_save_modifier(p, ability, self.calc_mod)

    # --- SISTEMA DE DERROTA (TPK) ---
    async def verificar_tpk(self, ctx, db):
        nomes_monstros = [m['nome'] for m in self.monstros_ativos]
        jogadores = [e['nome'] for e in self.ordem_combate if e['nome'] not in nomes_monstros]
        
        if not jogadores: return
        
        vivos = db.query(Personagem).filter(Personagem.nome.in_(jogadores), Personagem.hp > 0).count()
        
        if vivos == 0:
            embed = discord.Embed(
                title="💀 TOTAL PARTY KILL",
                description="A escuridão venceu. Todos os heróis caíram!",
                color=discord.Color.dark_red()
            )
            await ctx.send(embed=embed)
            self.monstros_ativos = []
            self.ordem_combate = []
            self.monstros_killed = []
            self._xp_awarded_vitoria = False
            self.auras = []
            self.aliados = []

    async def awardar_xp_vitoria(self, ctx, db):
        """
        Concede XP quando os monstros do combate acabam.
        A regra é: somar XP base por CR dos monstros derrotados, aplicar multiplicador por quantidade
        e dividir igualmente entre os personagens da fila de combate.
        """
        if self._xp_awarded_vitoria:
            return ""
        self._xp_awarded_vitoria = True

        if not self.monstros_killed:
            return ""

        nomes_participantes = [e["nome"] for e in self.ordem_combate]
        if not nomes_participantes:
            return ""

        participantes = (
            db.query(Personagem)
            .filter(Personagem.nome.in_(nomes_participantes), Personagem.hp > 0)
            .all()
        )
        if not participantes:
            return ""

        mortos = list(self.monstros_killed)
        slugs_unicos = sorted({m.get("slug") for m in mortos if m.get("slug")})
        xp_por_slug = {}

        async with httpx.AsyncClient(timeout=10.0) as client:
            for slug in slugs_unicos:
                if not slug:
                    continue
                url = f"https://www.dnd5eapi.co/api/2014/monsters/{slug}"
                try:
                    r = await client.get(url)
                    if r.status_code != 200:
                        xp_por_slug[slug] = 100
                        continue
                    dados = r.json()
                    cr = dados.get("challenge_rating") or dados.get("cr")
                    xp_base = cr_para_xp(cr)
                    xp_por_slug[slug] = int(xp_base) if xp_base is not None else 100
                except Exception:
                    xp_por_slug[slug] = 100

        xp_base_total = 0
        for m in mortos:
            slug = m.get("slug")
            xp_base_total += xp_por_slug.get(slug, 100)

        mult = multiplicador_grupo_monstros(len(mortos))
        xp_ajustado_total = int(xp_base_total * mult)

        n_part = len(participantes)
        xp_por_personagem = xp_ajustado_total // n_part
        resto = xp_ajustado_total % n_part

        subiram = []
        nomes_subiram = []
        for idx, p in enumerate(participantes):
            add = xp_por_personagem + (1 if idx < resto else 0)
            nivel_anterior, nivel_novo = aplicar_xp_personagem(p, add)
            if nivel_novo > nivel_anterior:
                nomes_subiram.append(p.nome)

        # Commit acontece no comando original (atacar/ciclo).
        self.monstros_killed = []

        if nomes_subiram:
            return f"🏆 **Vitória!** XP total ajustado: `{xp_ajustado_total}`. Subiram: {', '.join(nomes_subiram)}."
        return f"🏆 **Vitória!** XP total ajustado: `{xp_ajustado_total}`."

    # --- COMANDOS DE ADMIN / MESTRE ---
    @commands.command()
    @require_mestre()
    async def reviver(self, ctx, alvo: discord.Member):
        """Restaura a consciência de um herói (Mestre)."""
        db = SessionLocal()
        p = db.query(Personagem).filter(Personagem.discord_id == str(alvo.id)).first()
        if p:
            p.hp = 1
            db.commit()
            await ctx.send(f"✨ **{p.nome}** despertou do abismo (1 HP).")
        db.close()

    @commands.command()
    @require_mestre()
    async def limpar_combate(self, ctx):
        """Zera tudo."""
        self.monstros_ativos = []
        self.ordem_combate = []
        self.monstros_killed = []
        self._xp_awarded_vitoria = False
        self.auras = []
        self.aliados = []
        await ctx.send("🧹 O campo de batalha foi limpo.")

    # --- GERENCIAMENTO DE INIMIGOS (API) ---
    @commands.command()
    @require_mestre()
    async def horda(self, ctx, nome_monstro: str, qtd: int):
        """Invoca monstros diretamente da API 2014."""
        self.monstros_killed = []
        self._xp_awarded_vitoria = False

        slug = nome_monstro.lower().replace(" ", "-")
        url = f"https://www.dnd5eapi.co/api/2014/monsters/{slug}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return await ctx.send(f"❓ `{nome_monstro}` não encontrado na API.")
            dados = r.json()

        hp = dados.get('hit_points', 10)
        ca = dados.get('armor_class', [{'value': 10}])[0].get('value', 10)
        dex_mod = self.calc_mod(dados.get('dexterity', 10))
        dado_ini = random.randint(1, 20)
        resultado_ini = dado_ini + dex_mod

        for i in range(1, qtd + 1):
            n = f"{dados.get('name')} {i}"
            self.monstros_ativos.append({
                'nome': n, 'hp': hp, 'hp_max': hp, 'ca': ca, 'slug': slug, 'dex_mod': dex_mod,
            })
            self.ordem_combate.append({'nome': n, 'res': resultado_ini})
        
        self.ordem_combate.sort(key=lambda x: x['res'], reverse=True)
        await ctx.send(
            f"👹 **{qtd}x {dados.get('name')}** (HP: {hp} | CA: {ca}) surgiram!\n"
            f"🎲 Iniciativa da horda: `[{dado_ini}]` + DEX `{dex_mod}` = **{resultado_ini}**"
        )

    # --- COMANDOS DE LUTA ---
    @commands.command()
    async def iniciativa(self, ctx):
        """Entra na fila de combate."""
        db = SessionLocal()
        p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
        if not p: return await ctx.send("Crie sua ficha.")
        
        mod_dex = self.calc_mod(p.destreza)
        tem_vantagem = self._vantagem_iniciativa(p)
        dado_ini, rolagens, modo = self._rolar_d20(vantagem=tem_vantagem)
        total = dado_ini + mod_dex
        self.ordem_combate = [e for e in self.ordem_combate if e['nome'] != p.nome]
        self.ordem_combate.append({'nome': p.nome, 'res': total})
        self.ordem_combate.sort(key=lambda x: x['res'], reverse=True)
        detalhe_d20 = f"`[{rolagens[0]}]`"
        if len(rolagens) == 2:
            detalhe_d20 = f"`[{rolagens[0]}, {rolagens[1]}]` -> `{dado_ini}`"
        await ctx.send(
            f"🎲 **{p.nome}** iniciativa ({modo}): {detalhe_d20} + DEX `{mod_dex}` = **{total}**"
        )
        db.close()

    @commands.command()
    async def atacar(self, ctx, nome_monstro: str):
        """Ataca considerando Sede e Frenesi."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if p.hp <= 0: return await ctx.send(f"❌ **{p.nome}** está inconsciente!")

            alvo = next((m for m in self.monstros_ativos if m['nome'].lower() == nome_monstro.lower()), None)
            if not alvo: return await ctx.send("Alvo não encontrado.")

            mod = self.calc_mod(p.destreza if p.arma_tipo == "RANGED" else p.forca)
            msg = ""

            # --- LÓGICA DE VAMPIRO (SEDE) ---
            if hasattr(p, 'sede'):
                if p.sede >= 90:
                    msg += "⚠️ **FRENESI:** Você ataca como um animal! (-5 acerto)\n"
                    mod -= 5
                p.sede = min(100, p.sede + 2) # Esforço aumenta sede

            dado = random.randint(1, 20)
            prof = int(getattr(p, "proficiencia", 2) or 2)
            bonus_ataque = mod + prof
            total = dado + bonus_ataque

            msg += (
                f"⚔️ **{p.nome}** vs **{alvo['nome']}** | "
                f"`[{dado}]` + Mod `{mod}` + Prof `{prof}` = **{total}** (Bônus `{bonus_ataque}`) vs CA {alvo['ca']}\n"
            )
            
            falha_critica = dado == 1
            acerto_critico = dado == 20

            if falha_critica:
                msg += "💨 **Falha crítica (1 natural)!**"
            elif acerto_critico or total >= alvo['ca']:
                d_list = p.arma_dano.lower().split('d')
                dano_dados = sum([random.randint(1, int(d_list[1])) for _ in range(int(d_list[0]))])
                dano = dano_dados + mod
                if acerto_critico:
                    dano *= 2
                    msg += "🎯 **Acerto crítico (20 natural)!**\n"
                alvo['hp'] -= dano
                msg += (
                    f"💥 **DANO:** `({p.arma_dano}={dano_dados}) + Mod {mod}` = **{dano}** "
                    f"(HP Alvo: {max(0, alvo['hp'])})"
                )
                if alvo['hp'] <= 0:
                    # Marca o monstro derrotado para conceder XP quando o combate virar.
                    self.monstros_killed.append({'nome': alvo.get('nome'), 'slug': alvo.get('slug')})
                    self.monstros_ativos = [m for m in self.monstros_ativos if m['nome'] != alvo['nome']]
                    self.ordem_combate = [e for e in self.ordem_combate if e['nome'] != alvo['nome']]
                    msg += f"\n💀 **{alvo['nome']}** foi morto!"

                    # Se não sobrou nenhum monstro, recompensa a vitória.
                    if not self.monstros_ativos and not self._xp_awarded_vitoria:
                        xp_msg = await self.awardar_xp_vitoria(ctx, db)
                        if xp_msg:
                            msg += f"\n\n{xp_msg}"
            else:
                msg += "🛡️ Errou!"
            
            db.commit()
            await ctx.send(msg)
        finally: db.close()

    def _magia_fallback(self, slug_norm: str):
        return spell_fallback(slug_norm)

    def _buscar_magia_grimorio(self, db, personagem, slug_norm: str):
        q = db.query(Magia).filter(Magia.personagem_id == personagem.id)
        m = q.filter(Magia.index_en == slug_norm).first()
        if m:
            return m
        nome_espaco = slug_norm.replace("-", " ")
        return q.filter(Magia.nome_pt.ilike(nome_espaco)).first()

    async def _monstro_morreu(self, ctx, db, alvo, msg_extra: str = "") -> str:
        self.monstros_killed.append({"nome": alvo.get("nome"), "slug": alvo.get("slug")})
        self.monstros_ativos = [m for m in self.monstros_ativos if m["nome"] != alvo["nome"]]
        self.ordem_combate = [e for e in self.ordem_combate if e["nome"] != alvo["nome"]]
        msg = msg_extra + f"\n💀 **{alvo['nome']}** caiu!"
        if not self.monstros_ativos and not self._xp_awarded_vitoria:
            xp_msg = await self.awardar_xp_vitoria(ctx, db)
            if xp_msg:
                msg += f"\n\n{xp_msg}"
        return msg

    @commands.command()
    async def cast(self, ctx, spell_slug: str, *, nome_alvo: str = None):
        """
        Conjura magia. Use o slug da API (ex: fire-bolt, spirit-guardians).
        Magias de área (Spirit Guardians): só o slug, sem alvo.
        Magias de alvo único: `!cast fire-bolt NomeDoMonstro`
        """
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p or p.hp <= 0:
                return await ctx.send("❌ Você precisa de uma ficha ativa e conscientes.")

            # Tenta entender entradas como:
            # !cast flame strike "Young White Dragon 1"
            # !cast flame-strike Young White Dragon 1
            alvo_hint = clean_name(nome_alvo) if nome_alvo else None
            slug_norm = normalizar_index_magia(spell_slug)
            mag_db = self._buscar_magia_grimorio(db, p, slug_norm)
            fb = self._magia_fallback(slug_norm)
            info = MAGIA_ESPECIAL.get(slug_norm)

            if nome_alvo:
                texto_bruto = f"{spell_slug} {nome_alvo}".strip()
                tokens = texto_bruto.split()
                slugs_especiais = set(MAGIA_ESPECIAL.keys())
                slugs_fallback = {"fire-bolt", "magic-missile", "ray-of-frost"}
                slugs_grimorio = set()
                for m in db.query(Magia).filter(Magia.personagem_id == p.id).all():
                    if getattr(m, "index_en", None):
                        slugs_grimorio.add(normalizar_index_magia(m.index_en))
                    if getattr(m, "nome_pt", None):
                        slugs_grimorio.add(normalizar_index_magia(m.nome_pt))
                slugs_conhecidos = slugs_especiais | slugs_fallback | slugs_grimorio

                for i in range(1, len(tokens)):
                    slug_cand = normalizar_index_magia(" ".join(tokens[:i]))
                    alvo_cand = clean_name(" ".join(tokens[i:]))
                    if not alvo_cand:
                        continue
                    if slug_cand in slugs_conhecidos:
                        alvo_existe = any(
                            clean_name(m["nome"]).lower() == alvo_cand.lower()
                            for m in self.monstros_ativos
                        )
                        if alvo_existe:
                            slug_norm = slug_cand
                            alvo_hint = alvo_cand
                            mag_db = self._buscar_magia_grimorio(db, p, slug_norm)
                            fb = self._magia_fallback(slug_norm)
                            info = MAGIA_ESPECIAL.get(slug_norm)
                            break

            if info and info.get("tipo") == "requer_invocar":
                return await ctx.send(
                    "📌 Esta magia é invocada com `!invocar familiar <slug>` ou `!invocar morto_vivo <slug>` "
                    "(precisa tê-la no grimório)."
                )

            if info and info.get("tipo") == "aura_dano_area":
                if not mag_db:
                    return await ctx.send("❌ Aprenda **Spirit Guardians** no grimório (`!aprender spirit guardians`).")
                custo = int(mag_db.custo_mana or 0)
                if p.mana < custo:
                    return await ctx.send(f"⚠️ Mana insuficiente! ({p.mana}/{custo})")
                p.mana -= custo
                if getattr(p, "linhagem", "") == "Vampiro":
                    p.sede = min(100, int(getattr(p, "sede", 0) or 0) + 5)

                slot = max(3, int(mag_db.nivel_magia or 3))
                dano_str = dano_guardioes_por_slot(slot)
                self.auras = [
                    a
                    for a in self.auras
                    if not (a.get("dono_id") == str(ctx.author.id) and a.get("index") == "spirit-guardians")
                ]
                self.auras.append(
                    {
                        "index": "spirit-guardians",
                        "dono_id": str(ctx.author.id),
                        "dono_nome": p.nome,
                        "dano_str": dano_str,
                        "slot": slot,
                    }
                )
                db.commit()
                return await ctx.send(
                    f"✨ **{p.nome}** invoca **Guardiões Espirituais**! Uma aura de 4,5 m rodeia você.\n"
                    f"Use `!pulso_guardioes` no seu turno para aplicar **{dano_str}** (teste de **DES** vs CD {dc_conjuracao_generico(p)}) em cada inimigo."
                )

            if not alvo_hint:
                return await ctx.send("❌ Informe o alvo: `!cast fire-bolt NomeDoMonstro`.")

            alvo = next(
                (m for m in self.monstros_ativos if clean_name(m["nome"]).lower() == alvo_hint.lower()),
                None,
            )
            if not alvo:
                # Fallback: busca parcial para nomes com sufixos e variações leves.
                alvo = next(
                    (
                        m
                        for m in self.monstros_ativos
                        if alvo_hint.lower() in clean_name(m["nome"]).lower()
                        or clean_name(m["nome"]).lower() in alvo_hint.lower()
                    ),
                    None,
                )
            if not alvo:
                return await ctx.send("❌ Alvo não encontrado entre os monstros ativos.")

            custo = int(mag_db.custo_mana) if mag_db else (fb["custo"] if fb else None)
            if custo is None:
                return await ctx.send(f"❓ Magia `{spell_slug}` não encontrada no grimório nem no motor básico.")

            if p.mana < custo:
                return await ctx.send(f"⚠️ Mana insuficiente! ({p.mana}/{custo})")

            d_str = None
            if mag_db and mag_db.dano_base and "d" in str(mag_db.dano_base).lower():
                d_str = str(mag_db.dano_base).strip()
            elif fb:
                d_str = fb["dano"]
            if not d_str:
                return await ctx.send("Esta magia não tem dano de alvo único configurado no grimório.")

            p.mana -= custo
            if getattr(p, "linhagem", "") == "Vampiro":
                p.sede = min(100, int(getattr(p, "sede", 0) or 0) + 5)

            dano_final = rolar_string_dado(d_str)
            alvo["hp"] -= dano_final
            nome_mag = mag_db.nome_pt if mag_db else spell_slug.replace("-", " ").title()

            msg = f"✨ **{p.nome}** lança **{nome_mag}**!\n"
            msg += f"💥 **DANO:** `{d_str}` = **{dano_final}** | 👹 Alvo: `{max(0, alvo['hp'])} HP`"

            if alvo["hp"] <= 0:
                msg = await self._monstro_morreu(ctx, db, alvo, msg)

            db.commit()
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command(aliases=["guardioes", "area_guardioes"])
    async def pulso_guardioes(self, ctx):
        """No seu turno: aplica o dano da aura de Spirit Guardians em todos os inimigos (teste de DES)."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p or p.hp <= 0:
                return await ctx.send("❌ Você precisa estar em combate e consciente.")

            aura = next(
                (
                    a
                    for a in self.auras
                    if a.get("dono_id") == str(ctx.author.id) and a.get("index") == "spirit-guardians"
                ),
                None,
            )
            if not aura:
                return await ctx.send("❌ Você não tem **Spirit Guardians** ativo. Use `!cast spirit-guardians` antes.")

            if not self.monstros_ativos:
                return await ctx.send("Não há inimigos na área.")

            dc = dc_conjuracao_generico(p)
            dano_str = aura.get("dano_str", "3d8")
            linhas = [f"🌟 **{p.nome}** — pulso dos Guardiões (CD **{dc}** DES)\n"]

            for mon in list(self.monstros_ativos):
                if mon not in self.monstros_ativos:
                    continue
                dex_mod = int(mon.get("dex_mod", 0))
                d20, total = rolar_teste_resistencia(dex_mod)
                if total >= dc:
                    dano = max(0, rolar_string_dado(dano_str) // 2)
                    linhas.append(f"• **{mon['nome']}** DES `[{d20}]+{dex_mod}={total}` ✓ metade: **{dano}**")
                else:
                    dano = rolar_string_dado(dano_str)
                    linhas.append(f"• **{mon['nome']}** DES `[{d20}]+{dex_mod}={total}` ✗ total: **{dano}**")
                mon["hp"] -= dano
                if mon["hp"] <= 0:
                    linhas.append(await self._monstro_morreu(ctx, db, mon, ""))

            db.commit()
            await ctx.send("\n".join(linhas))
        finally:
            db.close()

    @commands.command()
    async def invocar(self, ctx, tipo: str, nome_slug: str):
        """
        `!invocar familiar owl` — precisa de Find Familiar no grimório.
        `!invocar morto_vivo zombie` — precisa de Animate Dead no grimório.
        """
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p or p.hp <= 0:
                return await ctx.send("❌ Crie uma ficha e esteja consciente.")

            t = tipo.lower().replace("-", "_")
            if t in ("familiar",):
                req_idx = "find-familiar"
                tipo_aliado = "familiar"
                self.aliados = [a for a in self.aliados if not (a["dono_id"] == str(ctx.author.id) and a["tipo"] == "familiar")]
            elif t in ("morto_vivo", "mortovivo", "undead", "zumbi"):
                req_idx = "animate-dead"
                tipo_aliado = "undead"
            else:
                return await ctx.send("Use `!invocar familiar <slug>` ou `!invocar morto_vivo <slug>` (slug da API, ex: owl, zombie).")

            tem = db.query(Magia).filter(Magia.personagem_id == p.id, Magia.index_en == req_idx).first()
            if not tem:
                return await ctx.send(f"❌ Você precisa aprender a magia correspondente no grimório (`{req_idx}`).")

            slug = nome_slug.lower().replace(" ", "-")
            url = f"https://www.dnd5eapi.co/api/2014/monsters/{slug}"
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return await ctx.send(f"❓ Criatura `{slug}` não encontrada na API.")
                dados = r.json()

            hp = dados.get("hit_points", 5)
            ca = dados.get("armor_class", [{"value": 10}])[0].get("value", 10)
            dex_mod = self.calc_mod(dados.get("dexterity", 10))
            nome_b = f"{dados.get('name')} ({tipo_aliado} de {p.nome})"

            self.aliados.append(
                {
                    "nome": nome_b,
                    "hp": hp,
                    "hp_max": hp,
                    "ca": ca,
                    "slug": slug,
                    "dex_mod": dex_mod,
                    "dono_id": str(ctx.author.id),
                    "tipo": tipo_aliado,
                }
            )
            db.commit()
            await ctx.send(
                f"✨ **{nome_b}** entra em cena! CA `{ca}` | HP `{hp}`.\n"
                f"Use `!iniciativa_aliado \"{nome_b}\"` e `!aliado_atacar \"{nome_b}\" <monstro>`."
            )
        finally:
            db.close()

    @commands.command()
    async def iniciativa_aliado(self, ctx, *, nome_aliado: str):
        ali = next((a for a in self.aliados if a["nome"].lower() == nome_aliado.lower()), None)
        if not ali:
            ali = next((a for a in self.aliados if nome_aliado.lower() in a["nome"].lower()), None)
        if not ali:
            return await ctx.send("❌ Aliado não encontrado. Use o nome exato da lista de invocações.")

        if ali["dono_id"] != str(ctx.author.id):
            return await ctx.send("❌ Só o dono controla este aliado.")

        mod_dex = int(ali.get("dex_mod", 0))
        dado_ini = random.randint(1, 20)
        total = dado_ini + mod_dex
        self.ordem_combate = [e for e in self.ordem_combate if e["nome"] != ali["nome"]]
        self.ordem_combate.append({"nome": ali["nome"], "res": total, "tipo": "aliado"})
        self.ordem_combate.sort(key=lambda x: x["res"], reverse=True)
        await ctx.send(
            f"🎲 **{ali['nome']}** iniciativa: `[{dado_ini}]` + DEX `{mod_dex}` = **{total}**"
        )

    @commands.command()
    async def aliado_atacar(self, ctx, nome_aliado: str, nome_monstro: str):
        """O dono ordena o aliado a atacar um monstro (usa o primeiro ataque da ficha da API)."""
        db = SessionLocal()
        try:
            ali = next((a for a in self.aliados if a["nome"].lower() == nome_aliado.lower()), None)
            if not ali:
                ali = next((a for a in self.aliados if nome_aliado.lower() in a["nome"].lower()), None)
            if not ali:
                return await ctx.send("❌ Aliado não encontrado.")
            if ali["dono_id"] != str(ctx.author.id):
                return await ctx.send("❌ Só o dono pode comandar este aliado.")

            alvo = next((m for m in self.monstros_ativos if m["nome"].lower() == nome_monstro.lower()), None)
            if not alvo:
                return await ctx.send("❌ Monstro não encontrado.")

            url = f"https://www.dnd5eapi.co/api/2014/monsters/{ali['slug']}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return await ctx.send("❌ Não foi possível carregar a ficha do aliado.")
                dados = r.json()

            acoes = [a for a in dados.get("actions", []) if "attack_bonus" in a]
            if not acoes:
                return await ctx.send("❌ Este aliado não tem ataque corpo-a-corpo/a distância na API.")
            ataque = acoes[0]

            dado = random.randint(1, 20)
            bonus = ataque.get("attack_bonus", 0)
            total = dado + bonus
            msg = f"🐾 **{ali['nome']}** vs **{alvo['nome']}** | `[{dado}]`+{bonus} = **{total}** vs CA {alvo['ca']}\n"
            falha_critica = dado == 1
            acerto_critico = dado == 20

            if falha_critica:
                msg += "💨 **Falha crítica (1 natural)!**"
            elif acerto_critico or total >= alvo["ca"]:
                dd = ataque.get("damage", [{}])[0].get("damage_dice", "1d4")
                dano_expr = dd.replace("-", "+")
                dano = rolar_string_dado(dano_expr)
                if acerto_critico:
                    dano *= 2
                    msg += "🎯 **Acerto crítico (20 natural)!**\n"
                alvo["hp"] -= dano
                msg += f"💥 **DANO:** `{dano_expr}` = **{dano}** (HP: {max(0, alvo['hp'])})"
                if alvo["hp"] <= 0:
                    msg = await self._monstro_morreu(ctx, db, alvo, msg)
                db.commit()
            else:
                msg += "🛡️ Errou!"
                db.commit()
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command()
    async def aliado_magias(self, ctx, *, nome_aliado: str):
        """Lista as magias do aliado invocado (se houver spellcasting na API)."""
        ali = next((a for a in self.aliados if a["nome"].lower() == nome_aliado.lower()), None)
        if not ali:
            ali = next((a for a in self.aliados if nome_aliado.lower() in a["nome"].lower()), None)
        if not ali:
            return await ctx.send("❌ Aliado não encontrado.")
        if ali["dono_id"] != str(ctx.author.id):
            return await ctx.send("❌ Só o dono pode consultar este aliado.")

        dados = await self._carregar_ficha_monstro(ali["slug"])
        if not dados:
            return await ctx.send("❌ Não foi possível carregar a ficha do aliado na API.")
        magias = self._extrair_magias_monstro(dados)
        if not magias:
            return await ctx.send(f"ℹ️ **{ali['nome']}** não possui lista de magias na API.")

        linhas = [f"📜 **Magias de {ali['nome']}**:"]
        for m in magias[:30]:
            linhas.append(f"- {m['nome']} (`{m['slug']}`)")
        if len(magias) > 30:
            linhas.append(f"*...e mais {len(magias) - 30}.*")
        await ctx.send("\n".join(linhas))

    @commands.command()
    async def aliado_cast(self, ctx, nome_aliado: str, magia_slug: str, *, nome_monstro: str):
        """
        O dono ordena o aliado a conjurar magia em um monstro.
        Uso: !aliado_cast "NOME_ALIADO" fire-bolt "Goblin 1"
        """
        db = SessionLocal()
        try:
            ali = next((a for a in self.aliados if a["nome"].lower() == nome_aliado.lower()), None)
            if not ali:
                ali = next((a for a in self.aliados if nome_aliado.lower() in a["nome"].lower()), None)
            if not ali:
                return await ctx.send("❌ Aliado não encontrado.")
            if ali["dono_id"] != str(ctx.author.id):
                return await ctx.send("❌ Só o dono pode comandar este aliado.")

            alvo = self._achar_monstro_ativo(nome_monstro)
            if not alvo:
                return await ctx.send("❌ Monstro alvo não encontrado.")

            dados = await self._carregar_ficha_monstro(ali["slug"])
            if not dados:
                return await ctx.send("❌ Não foi possível carregar a ficha do aliado.")
            magias = self._extrair_magias_monstro(dados)
            slug = magia_slug.lower().strip().replace(" ", "-")
            spell_ref = next((m for m in magias if m["slug"].lower() == slug), None)
            if not spell_ref:
                return await ctx.send(
                    f"❌ `{magia_slug}` não está na lista do aliado. Use `!aliado_magias \"{ali['nome']}\"`."
                )

            spell = await self._carregar_spell(slug)
            if not spell:
                return await ctx.send("❌ Não foi possível carregar os dados da magia.")

            dano_base, dano_expr = self._rolar_dano_spell(spell)
            if dano_base <= 0:
                return await ctx.send(
                    f"✨ **{ali['nome']}** conjurou **{spell_ref['nome']}**, "
                    "mas essa magia não tem dano automático configurado na API."
                )

            # CD aproximada para aliado conjurador (baseada no bloco da criatura).
            # 8 + bônus de proficiência aproximado pelo challenge rating + mod de conjuração genérico.
            # Para manter simples/consistente no bot, usamos um valor fixo de 12.
            dc_val = 12
            dc = (spell.get("dc", {}) or {})
            dc_type = (dc.get("dc_type", {}) or {}).get("index")
            if dc.get("dc_value"):
                dc_val = int(dc["dc_value"])

            dano_final = dano_base
            msg = f"✨ **{ali['nome']}** conjura **{spell_ref['nome']}** em **{alvo['nome']}**!\n"
            if dc_type:
                # Apenas DEX save para monstros está disponível no estado atual.
                if dc_type == "dex":
                    mod_save = int(alvo.get("dex_mod", 0))
                else:
                    mod_save = 0
                d20 = random.randint(1, 20)
                total_save = d20 + mod_save
                success_type = (dc.get("success_type") or "half").lower()
                passou = total_save >= int(dc_val)
                if passou and success_type == "none":
                    dano_final = 0
                elif passou:
                    dano_final = dano_base // 2
                msg += (
                    f"🎲 Save `{dc_type.upper()}`: `[{d20}]`+{mod_save} = **{total_save}** "
                    f"vs CD **{dc_val}**.\n"
                )

            alvo["hp"] -= int(dano_final)
            msg += f"💥 Dano: `{dano_expr}` => **{dano_final}** | HP de **{alvo['nome']}**: `{max(0, alvo['hp'])}`"
            if alvo["hp"] <= 0:
                msg = await self._monstro_morreu(ctx, db, alvo, msg)
            db.commit()
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command()
    async def despedir_aliado(self, ctx, *, nome_aliado: str):
        """Remove um aliado invocado (só o dono)."""
        ali = next((a for a in self.aliados if a["nome"].lower() == nome_aliado.lower()), None)
        if not ali:
            ali = next((a for a in self.aliados if nome_aliado.lower() in a["nome"].lower()), None)
        if not ali:
            return await ctx.send("❌ Aliado não encontrado.")
        if ali["dono_id"] != str(ctx.author.id):
            return await ctx.send("❌ Só o dono pode dispensar este aliado.")

        self.aliados = [a for a in self.aliados if a["nome"] != ali["nome"]]
        self.ordem_combate = [e for e in self.ordem_combate if e["nome"] != ali["nome"]]
        await ctx.send(f"👋 **{ali['nome']}** foi dispensado.")

    @commands.command()
    @require_mestre()
    async def mob_atacar(self, ctx, nome_instancia: str, alvo_user: discord.Member):
        """Ataque do inimigo contra o herói."""
        db = SessionLocal()
        try:
            mon = next((m for m in self.monstros_ativos if m['nome'].lower() == nome_instancia.lower()), None)
            if not mon: return
            
            url = f"https://www.dnd5eapi.co/api/2014/monsters/{mon['slug']}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                dados = r.json()

            ataque = [a for a in dados.get('actions', []) if 'attack_bonus' in a][0]
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo_user.id)).first()
            
            dado, bonus = random.randint(1, 20), ataque.get('attack_bonus', 0)
            total = dado + bonus
            ca_heroi = 10 + self.calc_mod(p.destreza)
            msg = f"👹 **{nome_instancia}** ataca **{p.nome}**! `[{dado}]`+{bonus} = **{total}** vs CA {ca_heroi}\n"
            falha_critica = dado == 1
            acerto_critico = dado == 20

            if falha_critica:
                msg += "💨 **Falha crítica (1 natural)!**"
            elif acerto_critico or total >= ca_heroi:
                d_dice = ataque.get('damage', [{}])[0].get('damage_dice', "1d4").replace('-', '+').split('+')
                dano_expr = ataque.get('damage', [{}])[0].get('damage_dice', "1d4").replace('-', '+')
                dano = rolar_string_dado(dano_expr)
                if acerto_critico:
                    dano *= 2
                    msg += "🎯 **Acerto crítico (20 natural)!**\n"
                p.hp = max(0, p.hp - dano)
                msg += f"💥 **ACERTOU!** Dano: `{dano_expr}` = **{dano}** | HP: {p.hp}"
                if p.hp == 0: msg += "\n🩸 **O HERÓI CAIU!**"
                db.commit()
                await self.verificar_tpk(ctx, db)
            else: msg += "🛡️ Errou!"
            await ctx.send(msg)
        finally: db.close()

    @commands.command()
    @require_mestre()
    async def mob_magias(self, ctx, *, nome_instancia: str):
        """Lista as magias disponíveis para um monstro ativo."""
        mon = self._achar_monstro_ativo(nome_instancia)
        if not mon:
            return await ctx.send("❌ Monstro não encontrado entre os ativos.")

        dados = await self._carregar_ficha_monstro(mon["slug"])
        if not dados:
            return await ctx.send("❌ Não foi possível carregar a ficha do monstro na API.")

        magias = self._extrair_magias_monstro(dados)
        if not magias:
            return await ctx.send(f"ℹ️ **{mon['nome']}** não possui lista de magias na API.")

        linhas = [f"🧙 **Magias de {mon['nome']}**:"]
        for m in magias[:30]:
            linhas.append(f"- {m['nome']} (`{m['slug']}`)")
        if len(magias) > 30:
            linhas.append(f"*...e mais {len(magias)-30}.*")
        await ctx.send("\n".join(linhas))

    @commands.command()
    @require_mestre()
    async def mob_cast(self, ctx, nome_instancia: str, magia_slug: str, alvo_user: discord.Member):
        """
        Conjura magia de um monstro ativo contra um jogador.
        Uso: !mob_cast "Goblin 1" fire-bolt @Jogador
        """
        db = SessionLocal()
        try:
            mon = self._achar_monstro_ativo(nome_instancia)
            if not mon:
                return await ctx.send("❌ Monstro não encontrado entre os ativos.")

            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo_user.id)).first()
            if not p:
                return await ctx.send("❌ Jogador alvo sem ficha.")

            dados = await self._carregar_ficha_monstro(mon["slug"])
            if not dados:
                return await ctx.send("❌ Não foi possível carregar a ficha do monstro.")

            magias = self._extrair_magias_monstro(dados)
            slug = magia_slug.lower().strip().replace(" ", "-")
            spell_ref = next((m for m in magias if m["slug"].lower() == slug), None)
            if not spell_ref:
                return await ctx.send(
                    f"❌ `{magia_slug}` não está na lista do monstro. Use `!mob_magias \"{mon['nome']}\"`."
                )

            spell = await self._carregar_spell(slug)
            if not spell:
                return await ctx.send("❌ Não foi possível carregar os dados da magia na API.")

            dano_base, dano_expr = self._rolar_dano_spell(spell)
            if dano_base <= 0:
                return await ctx.send(
                    f"✨ **{mon['nome']}** conjurou **{spell_ref['nome']}**, "
                    "mas essa magia não tem dano automático configurado na API."
                )

            dc = (spell.get("dc", {}) or {})
            dc_val = dc.get("dc_value")
            save_ability = (dc.get("dc_type", {}) or {}).get("index")

            msg = f"✨ **{mon['nome']}** conjura **{spell_ref['nome']}** em **{p.nome}**!\n"
            dano_final = dano_base
            if dc_val and save_ability:
                mod_save = self._mod_save_personagem(p, save_ability)
                d20 = random.randint(1, 20)
                total_save = d20 + mod_save
                success_type = (dc.get("success_type") or "half").lower()
                passou = total_save >= int(dc_val)
                if passou and success_type == "none":
                    dano_final = 0
                elif passou:
                    dano_final = dano_base // 2
                msg += (
                    f"🎲 Save `{save_ability.upper()}`: `[{d20}]`+{mod_save} = **{total_save}** "
                    f"vs CD **{dc_val}**.\n"
                )

            p.hp = max(0, int(p.hp or 0) - int(dano_final))
            msg += f"💥 Dano: `{dano_expr}` => **{dano_final}** | HP de **{p.nome}**: `{p.hp}`"
            if p.hp == 0:
                msg += "\n🩸 **O HERÓI CAIU!**"
            db.commit()
            await self.verificar_tpk(ctx, db)
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command()
    async def ordem(self, ctx):
        """Mostra turnos e status de sede."""
        if not self.ordem_combate: return await ctx.send("Sem combate ativo.")
        db = SessionLocal()
        msg = "⚔️ **ORDEM DE INICIATIVA:**\n"
        for i, e in enumerate(self.ordem_combate, 1):
            p = db.query(Personagem).filter(Personagem.nome == e['nome']).first()
            status = ""
            if p:
                if p.hp <= 0: status = " 💀 (Caído)"
                elif hasattr(p, 'sede'): status = f" 🩸 (Sede: {p.sede}%)"
            elif e.get("tipo") == "aliado":
                status = " 🐾 (Aliado)"
            msg += f"{i}º - **{e['nome']}** ({e['res']}){status}\n"
        await ctx.send(msg)
        db.close()

async def setup(bot):
    await bot.add_cog(CombateCog(bot))