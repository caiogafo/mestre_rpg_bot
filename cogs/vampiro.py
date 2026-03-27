import discord
import random
from discord.ext import commands
from database import SessionLocal, Personagem
from permissions import require_mestre

VAMPIRO_XP_THRESHOLDS = {
    1: 0,
    2: 100,
    3: 300,
    4: 700,
    5: 1500,
    6: 3000,
    7: 5500,
    8: 9000,
    9: 14000,
    10: 20000,
}

class VampiroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def calc_mod(self, valor):
        return (valor - 10) // 2

    def nivel_vampiro_por_xp(self, xp_total: int) -> int:
        nivel = 1
        for lvl in range(1, 11):
            if xp_total >= VAMPIRO_XP_THRESHOLDS[lvl]:
                nivel = lvl
        return nivel

    def aplicar_xp_vampiro(self, p, xp_gain: int):
        if xp_gain <= 0:
            return int(p.vampiro_level or 1), int(p.vampiro_level or 1)
        antes = int(p.vampiro_level or 1)
        p.vampiro_xp = int(getattr(p, "vampiro_xp", 0) or 0) + int(xp_gain)
        novo = self.nivel_vampiro_por_xp(int(p.vampiro_xp or 0))
        p.vampiro_level = novo
        return antes, novo

    @commands.command()
    async def ler_mente(self, ctx, alvo_user: discord.Member):
        """Habilidade Vampírica: Tenta antecipar os movimentos do alvo."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p: return await ctx.send("❌ Crie sua ficha primeiro.")
            if p.linhagem != "Vampiro":
                return await ctx.send("❌ Apenas vampiros podem usar esse poder.")

            # Verifica se já está em Frenesi
            if hasattr(p, 'sede') and p.sede > 80:
                return await ctx.send("🩸 **FOME CEGA!** Você não consegue se concentrar, o sangue é tudo o que importa!")

            d20 = random.randint(1, 20)
            mod_int = self.calc_mod(p.inteligencia)
            total = d20 + mod_int
            
            # Aumenta a sede ao usar poderes sobrenaturais
            if hasattr(p, 'sede'):
                p.sede += 5
                db.commit()
            
            msg = (
                f"👁️ **{p.nome}** foca seu olhar sobrenatural em **{alvo_user.display_name}**...\n"
                f"🎲 Teste mental: `[{d20}]` + INT `{mod_int}` = **{total}** (CD 12)\n"
            )
            if total >= 12:
                msg += "✅ **Sucesso!** Você lê as intenções dele. (+2 no próximo ataque)"
            else:
                msg += "❌ A mente do alvo é um labirinto ou ele resistiu ao seu toque."
            
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command()
    async def alimentar(self, ctx, nome_alvo: str):
        """Drena o sangue de um inimigo caído ou enfraquecido para reduzir a sede."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p: return await ctx.send("❌ Crie sua ficha primeiro.")
            if p.linhagem != "Vampiro":
                return await ctx.send("❌ Apenas vampiros podem se alimentar dessa forma.")
            
            # Recupera o combate para verificar se o alvo existe/morreu
            combate = self.bot.get_cog('CombateCog')
            if not combate: return await ctx.send("🚨 Sistema de combate não carregado.")
            
            # Lógica simples de alimentação
            p.sede = max(0, p.sede - 30)
            p.hp = min(p.hp_max, p.hp + 10)
            antes, novo = self.aplicar_xp_vampiro(p, 25)
            db.commit()

            msg = f"🩸 **{p.nome}** se alimenta! Sede `{p.sede}` e HP `{p.hp}/{p.hp_max}`."
            if novo > antes:
                msg += f"\n🧛 Evolução vampírica: **{antes} -> {novo}**!"
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command()
    @require_mestre()
    async def transformar(self, ctx, alvo: discord.Member, nova_linhagem: str):
        """Altera a linhagem do personagem. Ex: !transformar @Thalindor Vampiro"""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo.id)).first()
            if not p: return await ctx.send("❌ Personagem não encontrado.")

            p.linhagem = nova_linhagem.capitalize()
            
            if p.linhagem == "Vampiro":
                p.sede = 0
                if getattr(p, "vampiro_level", None) is None:
                    p.vampiro_level = 1
                if getattr(p, "vampiro_xp", None) is None:
                    p.vampiro_xp = 0
                msg = f"🧛 **{p.nome}** foi abraçado pelas trevas! Agora ele é um **Vampiro**."
            else:
                msg = f"🛡️ A linhagem de **{p.nome}** foi alterada para **{p.linhagem}**."
            
            db.commit()
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command(aliases=["sangue_vampirico"])
    @require_mestre()
    async def ganhar_sangue(self, ctx, alvo: discord.Member, quantidade: int):
        """Mestre: concede XP vampírico. Ex.: !ganhar_sangue @Tav 120"""
        if quantidade <= 0:
            return await ctx.send("❌ Informe uma quantidade positiva.")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo.id)).first()
            if not p:
                return await ctx.send("❌ Personagem não encontrado.")
            if p.linhagem != "Vampiro":
                return await ctx.send("❌ Esse personagem não é Vampiro.")

            antes, novo = self.aplicar_xp_vampiro(p, quantidade)
            db.commit()

            xp_atual = int(getattr(p, "vampiro_xp", 0) or 0)
            if novo >= 10:
                prox_txt = "Nível vampírico máximo."
            else:
                prox = novo + 1
                falta = max(0, VAMPIRO_XP_THRESHOLDS[prox] - xp_atual)
                prox_txt = f"Próximo Nv {prox} em `{VAMPIRO_XP_THRESHOLDS[prox]}` (faltam {falta})."

            msg = f"🩸 **{p.nome}** ganhou **{quantidade} XP vampírico**."
            if novo > antes:
                msg += f"\n🧛 Subiu: **{antes} -> {novo}**."
            msg += f"\nTotal: `{xp_atual}` XPv. {prox_txt}"
            await ctx.send(msg)
        finally:
            db.close()

    @commands.command()
    async def vampirismo(self, ctx):
        """Mostra nível e XP vampírico atual."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❌ Crie sua ficha primeiro.")
            if p.linhagem != "Vampiro":
                return await ctx.send("❌ Seu personagem não é Vampiro.")

            nivel = int(getattr(p, "vampiro_level", 1) or 1)
            xp_total = int(getattr(p, "vampiro_xp", 0) or 0)
            if nivel >= 10:
                extra = "Nível vampírico máximo."
            else:
                prox = nivel + 1
                falta = max(0, VAMPIRO_XP_THRESHOLDS[prox] - xp_total)
                extra = f"Próx. nível {prox}: `{VAMPIRO_XP_THRESHOLDS[prox]}` XPv (faltam {falta})."

            await ctx.send(
                f"🧛 **{p.nome}** — Nível vampírico `{nivel}` | XPv `{xp_total}`\n"
                f"🩸 Sede `{p.sede}%` | {extra}"
            )
        finally:
            db.close()

async def setup(bot):
    await bot.add_cog(VampiroCog(bot))