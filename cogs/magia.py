import discord
import httpx
import asyncio
from discord.ext import commands
from database import SessionLocal, Personagem, Magia
from referencia_magias import TABELA_MAGIAS
from spellcasting_dnd import classe_conjura_magia, limite_magias_grimorio

class MagiaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def calcular_limite(self, p):
        """Limite de magias no grimório conforme D&D 5e (conhecidas, livro ou preparadas)."""
        return limite_magias_grimorio(p)

    @commands.command()
    async def aprender(self, ctx, *, nome_magia: str):
        """Busca uma magia na API oficial de D&D e adiciona ao banco de dados."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p:
                return await ctx.send("❌ Você precisa criar uma ficha primeiro (`!criar_ficha`).")

            if not classe_conjura_magia(p.classe or ""):
                return await ctx.send(
                    "❌ Sua classe **não é conjuradora** (ou a ficha não tem classe válida). "
                    "Bárbaro, Guerreiro, Ladino e Monge não usam grimório de magia no D&D 5e."
                )

            # 1. Validação de Slots
            limite = self.calcular_limite(p)
            if limite <= 0:
                return await ctx.send("❌ Limite de grimório inválido. Verifique `!ficha` e a **classe** na ficha.")
            qtd_atual = db.query(Magia).filter(Magia.personagem_id == p.id).count()
            if qtd_atual >= limite:
                return await ctx.send(f"⚠️ **Grimório Cheio!** ({qtd_atual}/{limite} slots ocupados).")

            # 2. Limpeza da String
            nome_limpo = nome_magia.replace('"', '').replace("'", "").strip().lower()
            slug_magia = nome_limpo.replace(" ", "-")
            
            url = f"https://www.dnd5eapi.co/api/spells/{slug_magia}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MestreRPG/1.0",
                "Accept": "application/json"
            }

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 404:
                    return await ctx.send(f"❓ Magia `{nome_limpo}` não encontrada.")
                elif response.status_code != 200:
                    return await ctx.send(f"🚨 Erro na API (Status {response.status_code}).")

                dados = response.json()

            # --- BLOQUEIO DE NÍVEL (FIX) ---
            lvl_api = dados.get('level', 0)
            if lvl_api > 0:
                # Regra: Nível Personagem >= (Nível Magia * 2) - 1
                nivel_minimo = (lvl_api * 2) - 1
                if p.nivel < nivel_minimo:
                    return await ctx.send(
                        f"🚫 **Nível Insuficiente!** Magias de Nível `{lvl_api}` exigem que você "
                        f"seja pelo menos Nível `{nivel_minimo}`. Você é Nível `{p.nivel}`."
                    )
            # -------------------------------

            # 4. Extração de Dados
            dano_dict = dados.get('damage', {}).get('damage_at_slot_level', {})
            dano_base = dano_dict.get(str(lvl_api), "1") if dano_dict else "Efeito"

            # 5. Persistência (index = slug da API, ex: spirit-guardians)
            index_api = dados.get("index") or slug_magia
            nova_magia = Magia(
                nome_pt=dados.get('name'),
                index_en=index_api,
                nivel_magia=lvl_api,
                dano_base=dano_base,
                custo_mana=(lvl_api * 2) if lvl_api > 0 else 1,
                personagem_id=p.id
            )
            
            db.add(nova_magia)
            db.commit()
            await ctx.send(f"📖 **{nova_magia.nome_pt}** foi registrada no seu grimório!")

        except Exception as e:
            print(f"🚨 ERRO: {e}")
            await ctx.send("❌ Erro interno ao aprender magia.")
        finally:
            db.close()

    @commands.command(aliases=["tabela_magias"])
    async def referencia_magias(self, ctx):
        """Mostra a tabela de referência de magias (regra simplificada)."""
        embed = discord.Embed(
            title="📚 Referência de Magias (D&D 5e)",
            color=discord.Color.blue()
        )

        for titulo, lista in TABELA_MAGIAS.items():
            embed.add_field(
                name=titulo,
                value="\n".join(lista),
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command()
    async def grimorio(self, ctx):
        """Lista as magias aprendidas e o consumo de slots."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            if not p: return await ctx.send("❌ Crie sua ficha primeiro.")

            magias = db.query(Magia).filter(Magia.personagem_id == p.id).all()
            limite = self.calcular_limite(p)

            cls = (getattr(p, "classe", None) or "—").strip()
            desc = f"**{cls}** · Magias no grimório: `{len(magias)}/{limite}` *(limite D&D 5e: conhecidas, livro do mago ou preparadas)*"
            if not (getattr(p, "classe", None) or "").strip():
                desc = "⚠️ Ficha **sem classe** — recrie com `!criar_ficha` (raça + classe).\n" + desc
            embed = discord.Embed(
                title=f"📖 Grimório de {p.nome}",
                description=desc,
                color=discord.Color.purple()
            )

            if not magias:
                embed.description += "\n\n*Seu livro de magias está em branco.*"
            else:
                for m in magias:
                    info = f"Nível: {m.nivel_magia} | Dano: `{m.dano_base}` | 🔵 `{m.custo_mana}` Mana"
                    embed.add_field(name=f"✨ {m.nome_pt}", value=info, inline=False)

            await ctx.send(embed=embed)
        finally:
            db.close()

    @commands.command()
    async def esquecer_magia(self, ctx, *, nome: str):
        """Remove uma magia para liberar espaço no grimório."""
        db = SessionLocal()
        try:
            p = db.query(Personagem).filter(Personagem.discord_id == str(ctx.author.id)).first()
            m = db.query(Magia).filter(Magia.personagem_id == p.id, Magia.nome_pt.ilike(nome)).first()
            
            if not m: return await ctx.send("❓ Magia não encontrada no seu grimório.")
            
            db.delete(m)
            db.commit()
            await ctx.send(f"🚮 Magia **{nome}** esquecida. Slot liberado!")
        finally:
            db.close()

async def setup(bot):
    await bot.add_cog(MagiaCog(bot))