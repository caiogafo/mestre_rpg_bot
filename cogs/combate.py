import discord
import random
import httpx
from discord.ext import commands
from database import SessionLocal, Personagem, Magia
from xp_system import aplicar_xp_personagem, cr_para_xp, multiplicador_grupo_monstros
from magia_combate import (
    MAGIA_ESPECIAL,
    normalizar_index_magia,
    dano_guardioes_por_slot,
    rolar_string_dado,
    dc_conjuracao_generico,
    rolar_teste_resistencia,
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
        return (valor - 10) // 2

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
        resultado_ini = random.randint(1, 20) + dex_mod

        for i in range(1, qtd + 1):
            n = f"{dados.get('name')} {i}"
            self.monstros_ativos.append({
                'nome': n, 'hp': hp, 'hp_max': hp, 'ca': ca, 'slug': slug, 'dex_mod': dex_mod,
            })
            self.ordem_combate.append({'nome': n, 'res': resultado_ini})
        
        self.ordem_combate.sort(key=lambda x: x['res'], reverse=True)
        await ctx.send(f"👹 **{qtd}x {dados.get('name')}** (HP: {hp} | CA: {ca}) surgiram!")

    # --- COMANDOS DE LUTA ---
    @commands.command()
    async def iniciativa(self, ctx):
        """Entra na fila de combate."""
        db = SessionLocal()
        p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
        if not p: return await ctx.send("Crie sua ficha.")
        
        total = random.randint(1, 20) + self.calc_mod(p.destreza)
        self.ordem_combate = [e for e in self.ordem_combate if e['nome'] != p.nome]
        self.ordem_combate.append({'nome': p.nome, 'res': total})
        self.ordem_combate.sort(key=lambda x: x['res'], reverse=True)
        await ctx.send(f"🎲 **{p.nome}** rolou **{total}** de iniciativa!")
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
            total = dado + mod + p.proficiencia
            
            msg += f"⚔️ **{p.nome}** vs **{alvo['nome']}** | `[{dado}]`+{mod} = **{total}** vs CA {alvo['ca']}\n"
            
            if total >= alvo['ca']:
                d_list = p.arma_dano.lower().split('d')
                dano = sum([random.randint(1, int(d_list[1])) for _ in range(int(d_list[0]))]) + mod
                alvo['hp'] -= dano
                msg += f"💥 **DANO:** {dano} (HP Alvo: {max(0, alvo['hp'])})"
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
        return {
            "fire-bolt": {"dano": "1d10", "custo": 0},
            "magic-missile": {"dano": "3d4+3", "custo": 3},
            "ray-of-frost": {"dano": "1d8", "custo": 0},
        }.get(slug_norm)

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

            slug_norm = normalizar_index_magia(spell_slug)
            mag_db = self._buscar_magia_grimorio(db, p, slug_norm)
            fb = self._magia_fallback(slug_norm)

            info = MAGIA_ESPECIAL.get(slug_norm)
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

            if not nome_alvo:
                return await ctx.send("❌ Informe o alvo: `!cast fire-bolt NomeDoMonstro`.")

            alvo = next((m for m in self.monstros_ativos if m["nome"].lower() == nome_alvo.lower()), None)
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
            msg += f"💥 **DANO:** `{dano_final}` | 👹 Alvo: `{max(0, alvo['hp'])} HP`"

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

        total = random.randint(1, 20) + int(ali.get("dex_mod", 0))
        self.ordem_combate = [e for e in self.ordem_combate if e["nome"] != ali["nome"]]
        self.ordem_combate.append({"nome": ali["nome"], "res": total, "tipo": "aliado"})
        self.ordem_combate.sort(key=lambda x: x["res"], reverse=True)
        await ctx.send(f"🎲 **{ali['nome']}** rolou **{total}** de iniciativa!")

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

            if total >= alvo["ca"]:
                dd = ataque.get("damage", [{}])[0].get("damage_dice", "1d4")
                dano = rolar_string_dado(dd.replace("-", "+"))
                alvo["hp"] -= dano
                msg += f"💥 **DANO:** {dano} (HP: {max(0, alvo['hp'])})"
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
            msg = f"👹 **{nome_instancia}** ataca **{p.nome}**! `[{dado}]`+{bonus} = **{total}**\n"

            if total >= (10 + self.calc_mod(p.destreza)):
                d_dice = ataque.get('damage', [{}])[0].get('damage_dice', "1d4").replace('-', '+').split('+')
                dano = sum([random.randint(1, int(d_dice[0].split('d')[1])) for _ in range(int(d_dice[0].split('d')[0]))]) + (int(d_dice[1]) if len(d_dice)>1 else 0)
                p.hp = max(0, p.hp - dano)
                msg += f"💥 **ACERTOU!** Dano: {dano} | HP: {p.hp}"
                if p.hp == 0: msg += "\n🩸 **O HERÓI CAIU!**"
                db.commit()
                await self.verificar_tpk(ctx, db)
            else: msg += "🛡️ Errou!"
            await ctx.send(msg)
        finally: db.close()

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