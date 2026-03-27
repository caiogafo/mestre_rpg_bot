from discord.ext import commands

from database import SessionLocal, ConfigCampanha


def require_mestre():
    """
    Permite execução para:
    - Administrador do servidor
    - Usuário definido como mestre da campanha no servidor
    """

    async def predicate(ctx):
        if ctx.guild is None:
            return False

        if ctx.author.guild_permissions.administrator:
            return True

        db = SessionLocal()
        try:
            cfg = db.query(ConfigCampanha).filter(ConfigCampanha.guild_id == str(ctx.guild.id)).first()
            return bool(cfg and cfg.mestre_discord_id == str(ctx.author.id))
        finally:
            db.close()

    return commands.check(predicate)

