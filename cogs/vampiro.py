import discord
import random
from discord.ext import commands
from database import SessionLocal, Personagem

class VampiroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def calc_mod(self, valor):
        return (valor - 10) // 2

    @commands.command()
    async def ler_mente(self, ctx, alvo_user: discord.Member):
        """Habilidade Vampírica: Tenta antecipar os movimentos do alvo."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p: return await ctx.send("❌ Crie sua ficha primeiro.")

            # Verifica se já está em Frenesi
            if hasattr(p, 'sede') and p.sede > 80:
                return await ctx.send("🩸 **FOME CEGA!** Você não consegue se concentrar, o sangue é tudo o que importa!")

            dado = random.randint(1, 20) + self.calc_mod(p.inteligencia)
            
            # Aumenta a sede ao usar poderes sobrenaturais
            if hasattr(p, 'sede'):
                p.sede += 5
                db.commit()
            
            msg = f"👁️ **{p.nome}** foca seu olhar sobrenatural em **{alvo_user.display_name}**...\n"
            if dado >= 12:
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
            
            # Recupera o combate para verificar se o alvo existe/morreu
            combate = self.bot.get_cog('CombateCog')
            if not combate: return await ctx.send("🚨 Sistema de combate não carregado.")
            
            # Lógica simples de alimentação
            p.sede = max(0, p.sede - 30)
            p.hp = min(p.hp_max, p.hp + 10)
            db.commit()

            await ctx.send(f"🩸 **{p.nome}** se alimenta! A sede diminui para `{p.sede}` e recupera HP.")
        finally:
            db.close()

    @commands.command()
    async def transformar(self, ctx, alvo: discord.Member, nova_linhagem: str):
        """Altera a linhagem do personagem. Ex: !transformar @Thalindor Vampiro"""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo.id)).first()
            if not p: return await ctx.send("❌ Personagem não encontrado.")

            p.linhagem = nova_linhagem.capitalize()
            
            if p.linhagem == "Vampiro":
                p.sede = 0
                msg = f"🧛 **{p.nome}** foi abraçado pelas trevas! Agora ele é um **Vampiro**."
            else:
                msg = f"🛡️ A linhagem de **{p.nome}** foi alterada para **{p.linhagem}**."
            
            db.commit()
            await ctx.send(msg)
        finally:
            db.close()

async def setup(bot):
    await bot.add_cog(VampiroCog(bot))