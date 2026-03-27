import discord
from discord.ext import commands

from database import SessionLocal, Personagem, Item
from permissions import require_mestre
from xp_system import aplicar_xp_personagem


class XPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @require_mestre()
    async def ganhar_xp(self, ctx, quantidade: int, alvo_user: discord.Member):
        """Mestre: concede XP para o personagem do usuário informado."""
        if quantidade <= 0:
            return await ctx.send("❌ Informe uma quantidade de XP maior que 0.")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo_user.id)).first()
            if not p:
                return await ctx.send("❌ Esse usuário não possui ficha. Use `!criar_ficha` primeiro.")

            nivel_anterior, nivel_novo = aplicar_xp_personagem(p, quantidade)
            db.commit()

            if nivel_novo > nivel_anterior:
                return await ctx.send(
                    f"📈 **{p.nome}** ganhou **{quantidade} XP**!\n"
                    f"Subiu de nível: **{nivel_anterior} -> {nivel_novo}**."
                )

            await ctx.send(f"📈 **{p.nome}** ganhou **{quantidade} XP** (Nível atual: {nivel_novo}).")
        finally:
            db.close()

    @commands.command(aliases=["curar"])
    @require_mestre()
    async def icurar(self, ctx, alvo_user: discord.Member, pontos: int):
        """Mestre: cura direta de HP. Ex: !icurar @Jogador +10"""
        if pontos <= 0:
            return await ctx.send("❌ Informe pontos positivos. Ex.: `!icurar @Jogador +10`")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo_user.id)).first()
            if not p:
                return await ctx.send("❌ Esse usuário não possui ficha.")

            antes = int(p.hp or 0)
            p.hp = min(int(p.hp_max or 0), antes + int(pontos))
            curado = int(p.hp) - antes
            db.commit()
            await ctx.send(f"✨ **{p.nome}** recebeu cura de **{curado} HP** (`{p.hp}/{p.hp_max}`).")
        finally:
            db.close()

    @commands.command()
    @require_mestre()
    async def achar_item(
        self,
        ctx,
        alvo_user: discord.Member,
        nome_item: str,
        quantidade: int = 1,
        xp: int = 0,
    ):
        """
        Mestre: registra item no inventário do usuário e (opcionalmente) concede XP.

        Uso exemplo:
        !achar_item @Jogador "Espada Longa" 1 200
        """
        if quantidade <= 0:
            return await ctx.send("❌ Informe uma quantidade de itens maior que 0.")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(alvo_user.id)).first()
            if not p:
                return await ctx.send("❌ Esse usuário não possui ficha. Use `!criar_ficha` primeiro.")

            item = db.query(Item).filter(Item.personagem_id == p.id, Item.nome.ilike(nome_item)).first()
            if item:
                item.quantidade = int(item.quantidade or 0) + int(quantidade)
            else:
                item = Item(nome=nome_item, quantidade=quantidade, personagem_id=p.id)
                db.add(item)

            nivel_anterior = p.nivel
            if xp and xp > 0:
                aplicar_xp_personagem(p, int(xp))

            db.commit()

            msg = f"🎒 **{p.nome}** recebeu **{quantidade}x** `{nome_item}`."
            if xp and xp > 0:
                msg += f" E ganhou **{xp} XP**."
                if int(p.nivel) > int(nivel_anterior):
                    msg += f" Subiu de nível: **{nivel_anterior} -> {p.nivel}**."

            await ctx.send(msg)
        finally:
            db.close()

    @commands.command(aliases=["inv", "mochila"])
    async def inventario(self, ctx):
        """Mostra os itens do personagem."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❌ Use `!criar_ficha` primeiro.")

            itens = (
                db.query(Item)
                .filter(Item.personagem_id == p.id)
                .order_by(Item.nome)
                .all()
            )
            if not itens:
                return await ctx.send("🎒 Sua mochila está vazia.")

            embed = discord.Embed(title=f"🎒 Mochila de {p.nome}", color=discord.Color.green())
            for it in itens:
                embed.add_field(name=f"📦 {it.quantidade}x", value=f"`{it.nome}`", inline=False)
            await ctx.send(embed=embed)
        finally:
            db.close()

    @commands.command()
    async def usar(self, ctx, *, nome_item: str):
        """
        Usa 1 unidade de um item da mochila (somente consumo).
        A cura/efeito mecânico é aplicada manualmente pelo mestre.
        """
        nome_item = nome_item.strip().strip('"').strip("'")
        if not nome_item:
            return await ctx.send("❌ Informe o nome do item. Ex.: `!usar \"Poção de Cura\"`")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❌ Use `!criar_ficha` primeiro.")

            item = db.query(Item).filter(Item.personagem_id == p.id, Item.nome.ilike(nome_item)).first()
            if not item:
                return await ctx.send("❓ Item não encontrado na mochila.")

            atual = int(item.quantidade or 0)
            if atual <= 0:
                return await ctx.send("❓ Você não tem esse item disponível.")

            # Consome 1 unidade
            if atual == 1:
                db.delete(item)
            else:
                item.quantidade = atual - 1

            db.commit()
            await ctx.send(f"🧪 **{p.nome}** usou **1x `{item.nome}`** (item consumido).")
        finally:
            db.close()

    @commands.command()
    async def guardar(self, ctx, quantidade: int, *, nome_item: str):
        """Registra itens na sua mochila (loot narrativo, compras, etc.)."""
        if quantidade <= 0:
            return await ctx.send("❌ Informe uma quantidade maior que 0.")

        nome_item = nome_item.strip().strip('"').strip("'")
        if not nome_item:
            return await ctx.send("❌ Informe o nome do item.")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❌ Use `!criar_ficha` primeiro.")

            item = db.query(Item).filter(Item.personagem_id == p.id, Item.nome.ilike(nome_item)).first()
            if item:
                item.quantidade = int(item.quantidade or 0) + quantidade
            else:
                db.add(Item(nome=nome_item, quantidade=quantidade, personagem_id=p.id))

            db.commit()
            await ctx.send(f"🎒 **{p.nome}** guardou **{quantidade}x** `{nome_item}` na mochila.")
        finally:
            db.close()

    @commands.command(aliases=["tirar_mochila"])
    async def dropar(self, ctx, quantidade: int, *, nome_item: str):
        """Remove itens da mochila (descartar, usar, entregar, etc.)."""
        if quantidade <= 0:
            return await ctx.send("❌ Informe uma quantidade maior que 0.")

        nome_item = nome_item.strip().strip('"').strip("'")
        if not nome_item:
            return await ctx.send("❌ Informe o nome do item.")

        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❌ Use `!criar_ficha` primeiro.")

            item = db.query(Item).filter(Item.personagem_id == p.id, Item.nome.ilike(nome_item)).first()
            if not item:
                return await ctx.send("❓ Item não encontrado na mochila.")

            atual = int(item.quantidade or 0)
            if atual < quantidade:
                return await ctx.send(f"⚠️ Você só tem **{atual}x** `{item.nome}`.")

            if atual == quantidade:
                db.delete(item)
            else:
                item.quantidade = atual - quantidade

            db.commit()
            await ctx.send(f"🗑️ **{p.nome}** removeu **{quantidade}x** `{item.nome}` da mochila.")
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(XPCog(bot))

