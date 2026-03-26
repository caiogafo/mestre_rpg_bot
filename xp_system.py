from __future__ import annotations

from typing import Optional, Tuple


def calc_mod(valor: int) -> int:
    """Modificador estilo D&D: (valor - 10) // 2."""
    return (valor - 10) // 2


# XP clássico de D&D 5e para subir de nível (atinge o nível quando XP total >= threshold).
# Nível 1 começa em 0 XP.
XP_THRESHOLDS = {
    1: 0,
    2: 300,
    3: 900,
    4: 2700,
    5: 6500,
    6: 14000,
    7: 23000,
    8: 34000,
    9: 48000,
    10: 64000,
    11: 85000,
    12: 100000,
    13: 120000,
    14: 140000,
    15: 165000,
    16: 195000,
    17: 225000,
    18: 265000,
    19: 305000,
    20: 355000,
}

ASI_LEVELS = {4, 8, 12, 16, 19}

# Limite padrão de atributo em D&D 5e (sem itens mágicos).
LIMITE_ATRIBUTO_PADRAO = 20

# Aliases aceitos nos comandos (PT/EN abreviado).
STAT_MAP = {
    "for": "forca",
    "str": "forca",
    "forca": "forca",
    "des": "destreza",
    "dex": "destreza",
    "destreza": "destreza",
    "con": "constituicao",
    "cons": "constituicao",
    "constituicao": "constituicao",
    "int": "inteligencia",
    "inte": "inteligencia",
    "inteligencia": "inteligencia",
    "sab": "sabedoria",
    "wis": "sabedoria",
    "sabedoria": "sabedoria",
    "car": "carisma",
    "cha": "carisma",
    "carisma": "carisma",
}


def normalizar_atributo(s: str) -> Optional[str]:
    if not s:
        return None
    key = str(s).strip().lower()
    return STAT_MAP.get(key)


def aplicar_asi_5e(personagem, modo: int, stat1: str, stat2: Optional[str] = None) -> Tuple[bool, str]:
    """
    Aplica um ASI (Ability Score Increase) estilo D&D 5e.
    - modo 2: +2 em um único atributo (até o limite).
    - modo 1: +1 em dois atributos diferentes (cada um até o limite).

    Quando CON ou INT mudam, ajusta PV/Máx ou Mana/Máx como no livro para CON:
    +1 no modificador implica +Nível de PV máximos (e cura o mesmo tanto no HP atual, até o máximo).
    Para Mana usamos a mesma regra de escala (house rule alinhada ao bot).
    """
    pd = int(getattr(personagem, "pontos_disponiveis", 0) or 0)
    if pd <= 0:
        return False, "Você não tem ASI disponível (ganha nos níveis 4, 8, 12, 16 e 19)."

    col1 = normalizar_atributo(stat1)
    if not col1:
        return False, f"Atributo inválido: `{stat1}`. Use: for, des, con, int, sab, car."

    if modo == 2:
        if stat2 is not None:
            return False, "Para +2 em um atributo use apenas: `!asi 2 <atributo>`."
        val = int(getattr(personagem, col1, 10))
        if val + 2 > LIMITE_ATRIBUTO_PADRAO:
            return False, f"Não pode ultrapassar {LIMITE_ATRIBUTO_PADRAO} nesse atributo (está em {val})."
        old_val = val
        novo = val + 2
        setattr(personagem, col1, novo)
        _ajustar_vitais_por_mudanca_atributo(personagem, col1, old_val, novo)
        personagem.pontos_disponiveis = pd - 1
        return True, f"+2 em **{col1}** ({old_val} → {novo})."

    if modo == 1:
        if not stat2:
            return False, "Para +1 em dois atributos use: `!asi 1 <atributo> <atributo>`."
        col2 = normalizar_atributo(stat2)
        if not col2:
            return False, f"Atributo inválido: `{stat2}`."
        if col1 == col2:
            return False, "Os dois atributos precisam ser diferentes (regra do +1/+1)."
        v1 = int(getattr(personagem, col1, 10))
        v2 = int(getattr(personagem, col2, 10))
        if v1 + 1 > LIMITE_ATRIBUTO_PADRAO:
            return False, f"**{col1}** já está no limite ({v1})."
        if v2 + 1 > LIMITE_ATRIBUTO_PADRAO:
            return False, f"**{col2}** já está no limite ({v2})."
        setattr(personagem, col1, v1 + 1)
        _ajustar_vitais_por_mudanca_atributo(personagem, col1, v1, v1 + 1)
        setattr(personagem, col2, v2 + 1)
        _ajustar_vitais_por_mudanca_atributo(personagem, col2, v2, v2 + 1)
        personagem.pontos_disponiveis = pd - 1
        return True, f"+1 em **{col1}** ({v1} → {v1 + 1}) e +1 em **{col2}** ({v2} → {v2 + 1})."

    return False, "Modo inválido. Use `!asi 2 <atributo>` ou `!asi 1 <atributo> <atributo>`."


def _ajustar_vitais_por_mudanca_atributo(personagem, coluna: str, valor_antigo: int, valor_novo: int) -> None:
    """PHB: mudança no mod de CON altera PV máx como se sempre tivesse sido assim (+nível por +1 no mod)."""
    if coluna not in ("constituicao", "inteligencia"):
        return
    d_mod = calc_mod(valor_novo) - calc_mod(valor_antigo)
    if d_mod == 0:
        return
    nivel = max(1, int(getattr(personagem, "nivel", 1) or 1))
    delta = d_mod * nivel
    if coluna == "constituicao":
        personagem.hp_max = int(getattr(personagem, "hp_max", 0) or 0) + delta
        novo_hp = int(getattr(personagem, "hp", 0) or 0) + delta
        personagem.hp = min(novo_hp, int(getattr(personagem, "hp_max", 0) or 0))
    else:
        personagem.mana_max = int(getattr(personagem, "mana_max", 0) or 0) + delta
        nova_mana = int(getattr(personagem, "mana", 0) or 0) + delta
        personagem.mana = min(nova_mana, int(getattr(personagem, "mana_max", 0) or 0))


def nivel_por_xp(xp_total: int) -> int:
    nivel = 1
    for lvl in range(1, 21):
        if xp_total >= XP_THRESHOLDS[lvl]:
            nivel = lvl
    return nivel


def proficiencia_por_nivel(nivel: int) -> int:
    if nivel >= 17:
        return 6
    if nivel >= 13:
        return 5
    if nivel >= 9:
        return 4
    if nivel >= 5:
        return 3
    return 2


def hit_die_por_classe(classe: str) -> int:
    # Mapeamento simplificado para a progressão de PV.
    # (A maioria dos seus nomes de classe já está em PT no bot.)
    c = (classe or "").strip().lower()
    if c in {"mago", "feiticeiro"}:
        return 6
    if c in {"bruxo"}:
        return 8
    if c in {"clérigo", "clerigo", "druida", "bardo"}:
        return 8
    if c in {"paladino", "ranger"}:
        return 10
    if c in {"bárbaro", "barbaro"}:
        return 12
    if c in {"guerreiro", "fighter"}:
        return 10
    if c in {"ladino", "rougue"}:
        return 8
    # fallback: algo médio
    return 8


def mana_increase_por_nivel(classe: str, int_mod: int) -> int:
    # Como o seu sistema usa mana (não slots de magia), fazemos uma regra simples:
    # - classes de arcano (mago/feiticeiro/bruxo) sobem um pouco mais
    # - outras sobem menos
    c = (classe or "").strip().lower()
    if c in {"mago", "feiticeiro", "bruxo"}:
        base = 3
    else:
        base = 2
    inc = base + int_mod
    return max(1, inc)


def aplicar_xp_personagem(personagem, xp_adicional: int) -> Tuple[int, int]:
    """
    Aplica XP em um objeto `Personagem` (SQLAlchemy) e atualiza nível/PV/Mana/profici.
    Retorna: (nivel_anterior, nivel_novo)
    """
    if xp_adicional <= 0:
        return (personagem.nivel, personagem.nivel)

    nivel_anterior = int(personagem.nivel or 1)
    personagem.xp = int(personagem.xp or 0) + int(xp_adicional)

    nivel_novo = nivel_por_xp(int(personagem.xp))
    if nivel_novo <= nivel_anterior:
        return (nivel_anterior, nivel_novo)

    con_mod = calc_mod(int(getattr(personagem, "constituicao", 10)))
    int_mod = calc_mod(int(getattr(personagem, "inteligencia", 10)))

    hit_die = hit_die_por_classe(getattr(personagem, "classe", ""))
    hit_die_avg = (1 + hit_die) // 2  # média inteira para simplificar

    total_hp_increase = 0
    total_mana_increase = 0
    pontos_gain = 0

    for lvl in range(nivel_anterior + 1, nivel_novo + 1):
        hp_inc = max(1, hit_die_avg + con_mod)
        mana_inc = mana_increase_por_nivel(getattr(personagem, "classe", ""), int_mod)

        total_hp_increase += hp_inc
        total_mana_increase += mana_inc

        if lvl in ASI_LEVELS:
            pontos_gain += 1

    personagem.nivel = nivel_novo
    personagem.proficiencia = proficiencia_por_nivel(nivel_novo)

    personagem.hp_max = int(personagem.hp_max or 0) + total_hp_increase
    personagem.mana_max = int(personagem.mana_max or 0) + total_mana_increase

    # On-level-up: recupera ao máximo (regra simples para jogo rápido).
    personagem.hp = min(int(personagem.hp or 0) + total_hp_increase, int(personagem.hp_max))
    personagem.mana = min(int(personagem.mana or 0) + total_mana_increase, int(personagem.mana_max))

    personagem.pontos_disponiveis = int(getattr(personagem, "pontos_disponiveis", 0) or 0) + pontos_gain

    return (nivel_anterior, nivel_novo)


# Tabela CR -> XP (D&D 5e). Usada para estimar XP de monstros.
CR_XP = {
    "0": 10,
    "1/8": 25,
    "1/4": 50,
    "1/2": 100,
    "1": 200,
    "2": 450,
    "3": 700,
    "4": 1100,
    "5": 1800,
    "6": 2300,
    "7": 2900,
    "8": 3900,
    "9": 4800,
    "10": 5900,
    "11": 7200,
    "12": 8400,
    "13": 10000,
    "14": 11500,
    "15": 13000,
    "16": 15000,
    "17": 18000,
    "18": 20000,
    "19": 22000,
    "20": 25000,
}


def cr_para_xp(cr: str) -> Optional[int]:
    if cr is None:
        return None
    c = str(cr).strip()
    if c == "":
        return None
    # Algumas APIs retornam "½" ao invés de "1/2".
    c = c.replace("½", "1/2").replace("¼", "1/4").replace("⅛", "1/8")
    return CR_XP.get(c)


def multiplicador_grupo_monstros(qtd_monstros: int) -> float:
    # Multiplicadores simples (DMG) com base apenas na quantidade.
    if qtd_monstros <= 1:
        return 1.0
    if qtd_monstros == 2:
        return 1.5
    if 3 <= qtd_monstros <= 6:
        return 2.0
    if 7 <= qtd_monstros <= 10:
        return 2.5
    return 3.0

