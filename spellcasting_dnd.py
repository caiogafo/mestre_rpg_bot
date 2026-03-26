"""
Raças, classes e limite de magias no grimório (D&D 5e / SRD), alinhado às regras oficiais.
O bot usa o grimório como “magias que você registrou”; o limite depende da classe e do nível.
"""
from __future__ import annotations

from typing import Optional, Tuple

# --- Raças (SRD / mesa em PT; use hífen para nomes compostos: Meio-Elfo) ---
RACAS_CANONICAS = frozenset(
    {
        "Humano",
        "Anão",
        "Elfo",
        "Halfling",
        "Meio-Elfo",
        "Meio-Orc",
        "Draconato",
        "Gnomo",
        "Tiefling",
    }
)

ALIASES_RACA = {
    "anao": "Anão",
    "elfo": "Elfo",
    "halfling": "Halfling",
    "meioelfo": "Meio-Elfo",
    "meio-orc": "Meio-Orc",
    "meioorc": "Meio-Orc",
    "draconato": "Draconato",
    "gnomo": "Gnomo",
    "tiefling": "Tiefling",
    "humano": "Humano",
}

# --- Classes ---
CLASSES_CANONICAS = frozenset(
    {
        "Bárbaro",
        "Bardo",
        "Bruxo",
        "Clérigo",
        "Druida",
        "Guerreiro",
        "Ladino",
        "Mago",
        "Monge",
        "Paladino",
        "Ranger",
        "Feiticeiro",
    }
)

ALIASES_CLASSE = {
    "barbaro": "Bárbaro",
    "bardo": "Bardo",
    "bruxo": "Bruxo",
    "clerigo": "Clérigo",
    "druida": "Druida",
    "guerreiro": "Guerreiro",
    "ladino": "Ladino",
    "mago": "Mago",
    "monge": "Monge",
    "paladino": "Paladino",
    "patrulheiro": "Ranger",
    "ranger": "Ranger",
    "feiticeiro": "Feiticeiro",
}

# Conjuradores que podem usar !aprender (têm limite > 0 ou regra especial)
CLASSES_SEM_MAGIA = frozenset({"Bárbaro", "Guerreiro", "Ladino", "Monge"})

# Tipo de progressão para limite do grimório
TIPO_CONJURADOR = {
    "Mago": "spellbook",
    "Feiticeiro": "known_bs",
    "Bardo": "known_bs",
    "Bruxo": "known_warlock",
    "Clérigo": "prepared_wis",
    "Druida": "prepared_wis",
    "Paladino": "prepared_half_cha",
    "Ranger": "prepared_half_wis",
}


def mod(atributo: int) -> int:
    return (int(atributo) - 10) // 2


def normalizar_raca(texto: str) -> Tuple[Optional[str], Optional[str]]:
    """Retorna (canonica, erro_msg)."""
    if not texto or not str(texto).strip():
        return None, "Informe uma raça válida."
    raw = str(texto).strip()
    # Hífen vira espaço para alias, depois recompomos Meio-Elfo
    compact = raw.replace("-", "").replace(" ", "").lower()
    if compact in ALIASES_RACA:
        return ALIASES_RACA[compact], None
    # match direto
    for r in RACAS_CANONICAS:
        if r.lower() == raw.lower():
            return r, None
    return None, (
        f"Raça `{raw}` não reconhecida. Use uma das SRD: "
        f"{', '.join(sorted(RACAS_CANONICAS))} (ex.: `Meio-Elfo` ou `Meio-Elfo`)."
    )


def normalizar_classe(texto: str) -> Tuple[Optional[str], Optional[str]]:
    if not texto or not str(texto).strip():
        return None, "Informe uma classe válida."
    raw = str(texto).strip()
    compact = raw.replace("-", "").replace(" ", "").lower()
    if compact in ALIASES_CLASSE:
        return ALIASES_CLASSE[compact], None
    for c in CLASSES_CANONICAS:
        if c.lower() == raw.lower():
            return c, None
    return None, (
        f"Classe `{raw}` não reconhecida. Opções: "
        f"{', '.join(sorted(CLASSES_CANONICAS))}."
    )


# Bardo e Feiticeiro: magias conhecidas (PHB)
KNOWN_BARD_SORC = [
    0,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    14,
    15,
    15,
    16,
    16,
    17,
    17,
    18,
    18,
    19,
    19,
]

# Bruxo: magias conhecidas (PHB)
KNOWN_WARLOCK = [
    0,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    10,
    11,
    11,
    12,
    12,
    13,
    13,
    14,
    14,
    15,
    15,
]


def limite_magias_grimorio(personagem) -> int:
    """
    Limite de entradas no grimório do bot (magias registradas).
    - Mago: tamanho mínimo do livro (6 + 2 por nível acima do 1º).
    - Bardo/Feiticeiro: magias conhecidas.
    - Bruxo: magias conhecidas.
    - Clérigo/Druida: magias preparadas por dia (Sab + nível).
    - Paladino/Ranger: preparadas (atributo + metade do nível, mín. 1).
    - Sem magia: 0.
    """
    classe_raw = (getattr(personagem, "classe", None) or "").strip()
    ok, _ = normalizar_classe(classe_raw)
    if not ok:
        return 0
    classe = ok
    if classe in CLASSES_SEM_MAGIA:
        return 0

    n = max(1, min(20, int(getattr(personagem, "nivel", 1) or 1)))
    tipo = TIPO_CONJURADOR.get(classe)

    if tipo == "spellbook":
        # Livro: 6 no 1º nível + 2 por nível adicional (mínimo que o mago ganha ao subir).
        return 6 + 2 * (n - 1)

    if tipo == "known_bs":
        return KNOWN_BARD_SORC[n]

    if tipo == "known_warlock":
        return KNOWN_WARLOCK[n]

    if tipo == "prepared_wis":
        w = mod(int(getattr(personagem, "sabedoria", 10) or 10))
        return max(1, w + n)

    if tipo == "prepared_half_cha":
        c = mod(int(getattr(personagem, "carisma", 10) or 10))
        return max(1, c + n // 2)

    if tipo == "prepared_half_wis":
        w = mod(int(getattr(personagem, "sabedoria", 10) or 10))
        return max(1, w + n // 2)

    return 0


def classe_conjura_magia(classe: str) -> bool:
    ok, _ = normalizar_classe(classe or "")
    if not ok:
        return False
    return ok not in CLASSES_SEM_MAGIA
