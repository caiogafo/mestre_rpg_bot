import discord
from discord.ext import commands

from database import SessionLocal, ConfigCampanha
from permissions import require_mestre


class CampanhaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def definir_mestre(self, ctx, usuario: discord.Member):
        """Admin: define o mestre da campanha para este servidor."""
        if ctx.guild is None:
            return await ctx.send("❌ Este comando só funciona em servidor.")

        db = SessionLocal()
        try:
            cfg = db.query(ConfigCampanha).filter(ConfigCampanha.guild_id == str(ctx.guild.id)).first()
            if not cfg:
                cfg = ConfigCampanha(guild_id=str(ctx.guild.id), mestre_discord_id=str(usuario.id))
                db.add(cfg)
            else:
                cfg.mestre_discord_id = str(usuario.id)
            db.commit()
            await ctx.send(f"🎲 Mestre da campanha definido: **{usuario.display_name}**.")
        finally:
            db.close()

    @commands.command()
    async def mestre_atual(self, ctx):
        """Mostra quem é o mestre configurado neste servidor."""
        if ctx.guild is None:
            return await ctx.send("❌ Este comando só funciona em servidor.")

        db = SessionLocal()
        try:
            cfg = db.query(ConfigCampanha).filter(ConfigCampanha.guild_id == str(ctx.guild.id)).first()
            if not cfg:
                return await ctx.send("ℹ️ Nenhum mestre definido. Use `!definir_mestre @usuario` (admin).")
            await ctx.send(f"🎲 Mestre atual: <@{cfg.mestre_discord_id}>")
        finally:
            db.close()

    @commands.command()
    @require_mestre()
    async def remover_mestre(self, ctx):
        """Mestre/Admin: remove o mestre configurado neste servidor."""
        if ctx.guild is None:
            return await ctx.send("❌ Este comando só funciona em servidor.")

        db = SessionLocal()
        try:
            cfg = db.query(ConfigCampanha).filter(ConfigCampanha.guild_id == str(ctx.guild.id)).first()
            if not cfg:
                return await ctx.send("ℹ️ Não há mestre configurado.")
            db.delete(cfg)
            db.commit()
            await ctx.send("🧹 Configuração de mestre removida.")
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(CampanhaCog(bot))

