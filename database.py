from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# 🗄️ CONFIGURAÇÃO DO BANCO
engine = create_engine('sqlite:///rpg.db', echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class Personagem(Base):
    __tablename__ = 'personagens'
    id = Column(Integer, primary_key=True)
    discord_id = Column(String, unique=True, index=True) 
    nome = Column(String)
    raca = Column(String)
    classe = Column(String)
    
    # 📈 PROGRESSÃO (Regras D&D 5e)
    nivel = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    proficiencia = Column(Integer, default=2)
    pontos_disponiveis = Column(Integer, default=0) # Pontos ASI ganhos no Nível 4, 8...
    
    # ❤️ STATUS VITAIS
    hp = Column(Integer, default=20)
    hp_max = Column(Integer, default=20)
    mana = Column(Integer, default=10)
    mana_max = Column(Integer, default=10)
    
    # ⚔️ EQUIPAMENTO ATUAL (Para o sistema de !atacar)
    arma_equipada = Column(String, default="Punhos")
    arma_dano = Column(String, default="1d4")
    arma_tipo = Column(String, default="FOR") # FOR para corpo-a-corpo, DES para distância/finesse
    
    # 💪 ATRIBUTOS BASE
    forca = Column(Integer, default=10)
    destreza = Column(Integer, default=10)
    constituicao = Column(Integer, default=10)
    inteligencia = Column(Integer, default=10)
    sabedoria = Column(Integer, default=10)
    carisma = Column(Integer, default=10)
    
    # 🔗 RELACIONAMENTOS (Um personagem tem muitos itens e magias)
    inventario = relationship("Item", back_populates="dono", cascade="all, delete-orphan")
    grimorio = relationship("Magia", back_populates="dono", cascade="all, delete-orphan")

    # 🧛 VAMPIRO
    linhagem = Column(String, default="Humano") # O padrão agora é humano
    sede = Column(Integer, default=0) 
    vampiro_level = Column(Integer, default=1)

class Item(Base):
    __tablename__ = 'itens'
    id = Column(Integer, primary_key=True)
    nome = Column(String)
    quantidade = Column(Integer, default=1)
    personagem_id = Column(Integer, ForeignKey('personagens.id'))
    dono = relationship("Personagem", back_populates="inventario")

class Magia(Base):
    __tablename__ = 'magias'
    id = Column(Integer, primary_key=True)
    nome_pt = Column(String)
    index_en = Column(String)
    dano_base = Column(String, default="0d0")
    custo_mana = Column(Integer, default=2)
    alcance = Column(String, default="Self")
    nivel_magia = Column(Integer, default=0)
    personagem_id = Column(Integer, ForeignKey('personagens.id'))
    dono = relationship("Personagem", back_populates="grimorio")

# 🔨 CRIAÇÃO DAS TABELAS
def init_db():
    Base.metadata.create_all(engine)
    print("✅ Banco de dados sincronizado com sucesso!")

if __name__ == "__main__":
    init_db()