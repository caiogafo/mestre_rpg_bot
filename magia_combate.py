"""
Regras especiais de magias no combate (SRD / D&D 5e simplificado para o bot).
Identificação preferencial pelo `index` da API (ex: spirit-guardians, find-familiar).
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

# Comportamento por index da API dnd5eapi.co (spells)
MAGIA_ESPECIAL: Dict[str, Dict[str, Any]] = {
    "spirit-guardians": {
        "tipo": "aura_dano_area",
        "dado_base_nivel": 3,  # slot 3 = 3d8
        "save": "dex",
    },
    "find-familiar": {"tipo": "requer_invocar", "invocacao": "familiar"},
    "animate-dead": {"tipo": "requer_invocar", "invocacao": "undead"},
}


def normalizar_index_magia(s: str) -> str:
    if not s:
        return ""
    return s.strip().lower().replace(" ", "-").replace("_", "-")


def dano_guardioes_por_slot(nivel_slot: int) -> str:
    """Spirit Guardians: 3d8 no 3º nível; +1d8 por slot acima do 3º."""
    n = max(3, int(nivel_slot))
    qtd_d8 = 3 + max(0, n - 3)
    return f"{qtd_d8}d8"


def rolar_string_dado(s: str) -> int:
    """Ex.: '3d8', '2d6+3', '1d10'."""
    s = s.strip().lower().replace(" ", "")
    if not s:
        return 0
    total = 0
    # separa somas: 2d6+1d4+3
    partes = re.split(r"([+-])", s)
    if not partes:
        return 0
    primeiro = partes[0]
    if "d" in primeiro:
        total += _rolar_um_termo(primeiro)
    else:
        total += int(primeiro) if primeiro else 0
    i = 1
    while i < len(partes):
        op = partes[i]
        chunk = partes[i + 1] if i + 1 < len(partes) else ""
        if "d" in chunk:
            val = _rolar_um_termo(chunk)
        else:
            val = int(chunk) if chunk else 0
        if op == "+":
            total += val
        else:
            total -= val
        i += 2
    return total


def _rolar_um_termo(termo: str) -> int:
    if "d" not in termo:
        return int(termo)
    a, b = termo.split("d", 1)
    qtd = int(a) if a else 1
    faces = int(b)
    return sum(random.randint(1, faces) for _ in range(qtd))


def dc_conjuracao_generico(personagem) -> int:
    """CD típica de magia: 8 + proficiência + maior mod entre INT, SAB e CAR."""
    prof = int(getattr(personagem, "proficiencia", 2) or 2)
    mi = (int(getattr(personagem, "inteligencia", 10) or 10) - 10) // 2
    ms = (int(getattr(personagem, "sabedoria", 10) or 10) - 10) // 2
    mc = (int(getattr(personagem, "carisma", 10) or 10) - 10) // 2
    return 8 + prof + max(mi, ms, mc)


def rolar_teste_resistencia(mod_destreza: int) -> Tuple[int, int]:
    d = random.randint(1, 20)
    return d, d + mod_destreza
