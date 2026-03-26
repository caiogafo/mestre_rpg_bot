import os
import pathlib
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import engine, Base, Personagem, Item, Magia

Base.metadata.create_all(bind=engine)

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

class MestreBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        print("Carregando Módulos (Cogs)...")
        cogs_dir = pathlib.Path(__file__).resolve().parent / "cogs"
        for path in sorted(cogs_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            name = path.stem
            await self.load_extension(f"cogs.{name}")
            print(f"Módulo {path.name} carregado.")

    async def on_ready(self):
        print(f'{self.user} online! Arquitetura Modular Ativa.')

bot = MestreBot()

@bot.command()
@commands.has_permissions(administrator=True)
async def reload(ctx, extension):
    """Recarrega um módulo sem desligar o bot. Uso: !reload magia"""
    try:
        await bot.reload_extension(f'cogs.{extension}')
        await ctx.send(f'✅ Módulo `{extension}` atualizado com sucesso!')
    except Exception as e:
        await ctx.send(f'❌ Erro ao recarregar `{extension}`: {e}')


@bot.command(aliases=["limpar"])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    """
    Apaga mensagens recentes no canal (máx. 100 por vez; limite de 14 dias do Discord).
    Uso: !clear ou !clear 50 — alias: !limpar
    """
    if ctx.guild is None:
        return await ctx.send("❌ Este comando só funciona em um canal de servidor.")
    if amount < 1:
        return await ctx.send("❌ Informe um número entre 1 e 100.")
    if amount > 100:
        return await ctx.send("❌ Por segurança, o máximo por comando é **100** mensagens.")
    try:
        deleted = await ctx.channel.purge(limit=amount)
    except discord.Forbidden:
        return await ctx.send("❌ Não tenho permissão para **Gerenciar mensagens** neste canal.")
    except discord.HTTPException as e:
        return await ctx.send(f"❌ Falha ao apagar mensagens: `{e}`")
    msg = await ctx.send(f"🗑️ **{len(deleted)}** mensagem(ns) removida(s).")
    await msg.delete(delay=4)


bot.run(TOKEN)