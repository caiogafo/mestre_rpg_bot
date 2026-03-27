import discord
import random
from discord.ext import commands
from database import SessionLocal, Personagem, Item
from xp_system import XP_THRESHOLDS, aplicar_asi_5e
from spellcasting_dnd import CLASSES_CANONICAS, RACAS_CANONICAS, normalizar_classe, normalizar_raca
from xp_system import hit_die_por_classe

class PersonagemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def calc_mod(self, valor):
        return (valor - 10) // 2

    @commands.command()
    async def criar_ficha(
        self,
        ctx,
        nome: str,
        for_stat: int,
        dex: int,
        con: int,
        int_stat: int,
        sab: int,
        car: int,
        raca: str,
        classe: str,
        linhagem: str = "Humano",
    ):
        """
        Cria a ficha: atributos, raça e classe (D&D 5e SRD). Linhagem extra: Humano ou Vampiro.
        Uso: !criar_ficha Nome FOR DES CON INT SAB CAR Raca Classe [Linhagem]
        Ex.: !criar_ficha Elminster 10 12 14 16 10 8 Humano Mago
        Raças compostas: Meio-Elfo, Meio-Orc (um token com hífen).
        """
        db = SessionLocal()
        try:
            discord_id_str = str(ctx.author.id)
            existe = db.query(Personagem).filter(Personagem.discord_id == discord_id_str).first()
            if existe:
                return await ctx.send("❌ Você já possui uma ficha ativa!")

            raca_ok, err_r = normalizar_raca(raca)
            if not raca_ok:
                return await ctx.send(f"❌ {err_r}")
            classe_ok, err_c = normalizar_classe(classe)
            if not classe_ok:
                return await ctx.send(f"❌ {err_c}")

            nova_linhagem = linhagem.strip().capitalize()
            if nova_linhagem not in ("Humano", "Vampiro"):
                return await ctx.send("❌ Linhagem deve ser `Humano` ou `Vampiro` (trama do bot).")

            novo_p = Personagem(
                discord_id=discord_id_str,
                nome=nome,
                raca=raca_ok,
                classe=classe_ok,
                forca=for_stat,
                destreza=dex,
                constituicao=con,
                inteligencia=int_stat,
                sabedoria=sab,
                carisma=car,
                hp=10 + self.calc_mod(con),
                hp_max=10 + self.calc_mod(con),
                mana=10 + self.calc_mod(int_stat),
                mana_max=10 + self.calc_mod(int_stat),
                linhagem=nova_linhagem,
                sede=0,
                vampiro_level=1 if nova_linhagem == "Vampiro" else 0,
                arma_dano="1d4", # Inicial padrão
                arma_tipo="MELEE",
                proficiencia=2
            )
            novo_p.dados_vida_total = 1
            novo_p.dados_vida_disponiveis = 1

            db.add(novo_p)
            db.commit()
            await ctx.send(
                f"✅ **{nome}** — {raca_ok} **{classe_ok}** (linhagem: {nova_linhagem}) registrado com sucesso!"
            )
        except Exception as e:
            print(f"🚨 ERRO NA CRIAÇÃO: {e}")
            await ctx.send("❌ Erro ao salvar ficha.")
        finally:
            db.close()

    @commands.command()
    async def racas(self, ctx):
        """Lista raças SRD aceitas em !criar_ficha."""
        await ctx.send("**Raças (SRD):** " + ", ".join(sorted(RACAS_CANONICAS)) + "\n*Nomes compostos com hífen:* `Meio-Elfo`, `Meio-Orc`")

    @commands.command()
    async def classes(self, ctx):
        """Lista classes aceitas em !criar_ficha."""
        await ctx.send("**Classes:** " + ", ".join(sorted(CLASSES_CANONICAS)) + " — `Patrulheiro` conta como **Ranger**")

    @commands.command(aliases=['status', 'perfil'])
    async def ficha(self, ctx):
        """Exibe as estatísticas completas, sede e equipamentos."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p: return await ctx.send("❓ Use `!criar_ficha` primeiro.")

            embed = discord.Embed(title=f"📜 Ficha: {p.nome}", color=discord.Color.red() if p.linhagem == "Vampiro" else discord.Color.blue())

            rc = (getattr(p, "raca", None) or "?").strip()
            cl = (getattr(p, "classe", None) or "?").strip()
            embed.add_field(name="🏷️ Raça / Classe", value=f"{rc} · **{cl}**", inline=False)
            
            stats = f"STR: `{p.forca}` | DEX: `{p.destreza}` | CON: `{p.constituicao}`\n"
            stats += f"INT: `{p.inteligencia}` | WIS: `{p.sabedoria}` | CHA: `{p.carisma}`"
            embed.add_field(name="📊 Atributos", value=stats, inline=False)

            nivel_atual = int(p.nivel or 1)
            vital = f"📊 Nível: `{nivel_atual}`\n"
            vital += f"❤️ HP: `{p.hp}/{p.hp_max}` | 🔵 Mana: `{p.mana}/{p.mana_max}`"
            if p.linhagem == "Vampiro":
                vital += f"\n🩸 Sede: `{p.sede}%` | 🧬 Nível Vampírico: `{p.vampiro_level}`"
            
            embed.add_field(name="🛡️ Status", value=vital, inline=True)
            nome_arma = (getattr(p, "arma_equipada", None) or "").strip() or "Punhos"
            embed.add_field(
                name="⚔️ Arma",
                value=f"**{nome_arma}**\nDano: `{p.arma_dano}` | Tipo: `{p.arma_tipo}`",
                inline=True,
            )

            # XP e progressão de nível (tabela clássica D&D)
            xp_total = int(p.xp or 0)
            if nivel_atual >= 20:
                xp_info = f"`{xp_total}` XP | Nível máximo."
            else:
                proximo_nivel = nivel_atual + 1
                proximo_threshold = XP_THRESHOLDS.get(proximo_nivel)
                if proximo_threshold is None:
                    xp_info = f"`{xp_total}` XP"
                else:
                    faltam = max(0, int(proximo_threshold) - xp_total)
                    xp_info = f"`{xp_total}` XP | Próximo ({proximo_nivel}): `{proximo_threshold}` XP (faltam {faltam})"

            embed.add_field(name="📈 XP", value=xp_info, inline=False)
            dv_total = int(getattr(p, "dados_vida_total", max(1, nivel_atual)) or max(1, nivel_atual))
            dv_disp = int(getattr(p, "dados_vida_disponiveis", dv_total) or dv_total)
            embed.add_field(name="🛌 Descanso", value=f"Dados de Vida: `{dv_disp}/{dv_total}`", inline=False)

            itens = db.query(Item).filter(Item.personagem_id == p.id).order_by(Item.nome).all()
            if itens:
                linhas = []
                for it in itens[:20]:
                    q = int(it.quantidade or 0)
                    linhas.append(f"• `{q}x` {it.nome}")
                mochila_txt = "\n".join(linhas)
                if len(itens) > 20:
                    mochila_txt += f"\n*…e mais {len(itens) - 20} tipo(s) de item.*"
            else:
                mochila_txt = "*Vazia.* `!guardar` para registrar itens · `!mochila` para ver tudo."
            if len(mochila_txt) > 1000:
                mochila_txt = mochila_txt[:997] + "…"
            embed.add_field(name="🎒 Mochila", value=mochila_txt, inline=False)

            asi_disp = int(getattr(p, "pontos_disponiveis", 0) or 0)
            embed.add_field(
                name="🎯 ASI (D&D 5e)",
                value=f"Pendentes: `{asi_disp}` — use `!asi 2 for` (+2) ou `!asi 1 for des` (+1/+1).",
                inline=False,
            )
            
            await ctx.send(embed=embed)
        finally:
            db.close()

    @commands.command()
    async def asi(self, ctx, modo: int, stat1: str, stat2: str = None):
        """
        Aumento de Atributo (ASI) estilo D&D 5e, ao subir de nível nos níveis 4, 8, 12, 16 e 19.
        - !asi 2 for — +2 em Força (ou des, con, int, sab, car)
        - !asi 1 for des — +1 em Força e +1 em Destreza
        """
        if modo not in (1, 2):
            return await ctx.send(
                "Use `!asi 2 <atributo>` (+2 em um) ou `!asi 1 <atributo> <atributo>` (+1 em dois)."
            )

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❓ Use `!criar_ficha` primeiro.")

            ok, msg = aplicar_asi_5e(p, modo, stat1, stat2)
            if not ok:
                return await ctx.send(f"❌ {msg}")
            db.commit()
            await ctx.send(f"✅ **{p.nome}**: {msg}")
        finally:
            db.close()

    @commands.command()
    async def equipar(self, ctx, nome_arma: str):
        """Define o dano e tipo da arma do personagem."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p: return await ctx.send("Crie sua ficha primeiro.")

            # Lógica simples para armas comuns (Pode ser expandida via API)
            armas = {
                "longbow": ("Longbow", "1d8", "RANGED"),
                "shortbow": ("Shortbow", "1d6", "RANGED"),
                "greatsword": ("Greatsword", "2d6", "MELEE"),
                "longsword": ("Longsword", "1d8", "MELEE"),
                "dagger": ("Dagger", "1d4", "MELEE"),
            }

            chave = nome_arma.lower().strip()
            arma = armas.get(chave)
            if arma:
                nome_exib, dano, tipo = arma
                p.arma_equipada = nome_exib
                p.arma_dano, p.arma_tipo = dano, tipo
                db.commit()
                await ctx.send(f"⚔️ **{p.nome}** agora empunha um(a) **{nome_exib}**!")
            else:
                await ctx.send("❌ Arma não encontrada na lista básica.")
        finally:
            db.close()

    @commands.command()
    async def aprender_magia(self, ctx, nome: str, level: int, dano: str):
        """Registra uma magia no herói (Simulação de Grimório)."""
        # Nota: Como ainda não temos uma tabela de magias complexa, 
        # estamos apenas confirmando o registro narrativo aqui.
        await ctx.send(f"✨ **{nome}** (Nível {level}) foi adicionada ao seu grimório!")

    @commands.command()
    async def descanso_curto(self, ctx, dados: int = 1):
        """
        Descanso curto: gasta Dados de Vida para recuperar HP.
        Uso: !descanso_curto [qtd_dados]
        """
        if dados <= 0:
            return await ctx.send("❌ Informe uma quantidade de dados de vida maior que 0.")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❓ Use `!criar_ficha` primeiro.")

            nivel = int(getattr(p, "nivel", 1) or 1)
            p.dados_vida_total = int(getattr(p, "dados_vida_total", nivel) or nivel)
            if p.dados_vida_total < nivel:
                p.dados_vida_total = nivel
            p.dados_vida_disponiveis = int(getattr(p, "dados_vida_disponiveis", p.dados_vida_total) or p.dados_vida_total)
            if p.dados_vida_disponiveis > p.dados_vida_total:
                p.dados_vida_disponiveis = p.dados_vida_total

            gastar = min(int(dados), int(p.dados_vida_disponiveis))
            if gastar <= 0:
                return await ctx.send("❌ Você não tem Dados de Vida disponíveis. Faça `!descanso_longo`.")

            faces = hit_die_por_classe(getattr(p, "classe", ""))
            con_mod = self.calc_mod(int(getattr(p, "constituicao", 10) or 10))
            rolagens = [max(1, random.randint(1, faces) + con_mod) for _ in range(gastar)]
            cura_total = sum(rolagens)

            hp_antes = int(p.hp or 0)
            p.hp = min(int(p.hp_max or 0), hp_antes + cura_total)
            curado = int(p.hp) - hp_antes
            p.dados_vida_disponiveis = int(p.dados_vida_disponiveis) - gastar

            # House rule: Bruxo recupera mana no descanso curto.
            mana_extra = ""
            if (getattr(p, "classe", "") or "").strip().lower() == "bruxo":
                p.mana = int(p.mana_max or p.mana)
                mana_extra = f"\n🔵 Mana restaurada: `{p.mana}/{p.mana_max}` (regra de Bruxo)."

            db.commit()
            await ctx.send(
                f"🛌 **{p.nome}** fez descanso curto e gastou **{gastar}** DV (`d{faces}`).\n"
                f"❤️ Recuperou **{curado} HP** (`{p.hp}/{p.hp_max}`).\n"
                f"🎲 Rolagens: `{', '.join(str(r) for r in rolagens)}`\n"
                f"📉 DV restantes: `{p.dados_vida_disponiveis}/{p.dados_vida_total}`"
                f"{mana_extra}"
            )
        finally:
            db.close()

    @commands.command()
    async def descanso_longo(self, ctx):
        """
        Descanso longo: restaura HP/Mana e recupera metade dos Dados de Vida (mínimo 1).
        """
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❓ Use `!criar_ficha` primeiro.")

            nivel = int(getattr(p, "nivel", 1) or 1)
            p.dados_vida_total = int(getattr(p, "dados_vida_total", nivel) or nivel)
            if p.dados_vida_total < nivel:
                p.dados_vida_total = nivel
            p.dados_vida_disponiveis = int(getattr(p, "dados_vida_disponiveis", p.dados_vida_total) or p.dados_vida_total)

            recuperar_dv = max(1, p.dados_vida_total // 2)
            dv_antes = p.dados_vida_disponiveis
            p.dados_vida_disponiveis = min(p.dados_vida_total, p.dados_vida_disponiveis + recuperar_dv)
            dv_ganhos = p.dados_vida_disponiveis - dv_antes

            p.hp = int(p.hp_max or p.hp)
            p.mana = int(p.mana_max or p.mana)
            if getattr(p, "linhagem", "") == "Vampiro":
                p.sede = max(0, int(getattr(p, "sede", 0) or 0) - 20)

            db.commit()
            extra_vamp = ""
            if getattr(p, "linhagem", "") == "Vampiro":
                extra_vamp = f"\n🩸 Sede após descanso: `{p.sede}%`."

            await ctx.send(
                f"🌙 **{p.nome}** concluiu um descanso longo.\n"
                f"❤️ HP: `{p.hp}/{p.hp_max}` | 🔵 Mana: `{p.mana}/{p.mana_max}`\n"
                f"🎲 Dados de Vida recuperados: `+{dv_ganhos}` → `{p.dados_vida_disponiveis}/{p.dados_vida_total}`"
                f"{extra_vamp}"
            )
        finally:
            db.close()

async def setup(bot):
    await bot.add_cog(PersonagemCog(bot))