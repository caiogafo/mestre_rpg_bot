from __future__ import annotations

import random
from typing import Any, Callable


SPELL_FALLBACK = {
    "fire-bolt": {"dano": "1d10", "custo": 0},
    "magic-missile": {"dano": "3d4+3", "custo": 3},
    "ray-of-frost": {"dano": "1d8", "custo": 0},
}


def calc_mod(valor: int) -> int:
    return (int(valor) - 10) // 2


def roll_d20(vantagem: bool = False, desvantagem: bool = False) -> tuple[int, list[int], str]:
    """Rola d20 normal, com vantagem ou desvantagem."""
    if vantagem and not desvantagem:
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        return max(r1, r2), [r1, r2], "vantagem"
    if desvantagem and not vantagem:
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        return min(r1, r2), [r1, r2], "desvantagem"
    r = random.randint(1, 20)
    return r, [r], "normal"


def has_initiative_advantage(personagem) -> bool:
    """Regra atual: Bárbaro nível 7+ (Instinto Feral) tem vantagem na iniciativa."""
    classe = (getattr(personagem, "classe", "") or "").strip().lower()
    nivel = int(getattr(personagem, "nivel", 1) or 1)
    return classe in {"barbaro", "bárbaro"} and nivel >= 7


def find_active_monster(monstros_ativos: list[dict[str, Any]], nome_instancia: str):
    alvo = next((m for m in monstros_ativos if m["nome"].lower() == nome_instancia.lower()), None)
    if alvo:
        return alvo
    return next((m for m in monstros_ativos if nome_instancia.lower() in m["nome"].lower()), None)


def extract_monster_spells(dados_monstro: dict[str, Any]) -> list[dict[str, str]]:
    """
    Extrai magias de special_abilities.spellcasting (formato dnd5eapi).
    Retorna lista de dicts: {"nome": "...", "slug": "..."} sem duplicados.
    """
    resultado = []
    vistos = set()
    for ab in dados_monstro.get("special_abilities", []) or []:
        sc = ab.get("spellcasting")
        if not sc:
            continue
        for s in sc.get("spells", []) or []:
            nome = (s.get("name") or "").strip()
            url = s.get("url") or ""
            slug = url.rstrip("/").split("/")[-1] if url else nome.lower().replace(" ", "-")
            if not nome or not slug:
                continue
            chave = (nome.lower(), slug.lower())
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append({"nome": nome, "slug": slug})
    return sorted(resultado, key=lambda x: x["nome"].lower())


def roll_spell_damage(spell_data: dict[str, Any], roll_string: Callable[[str], int]) -> tuple[int, str]:
    """Retorna (dano_rolado, expressão_dano)."""
    dmg = spell_data.get("damage", {}) or {}
    d_slot = dmg.get("damage_at_slot_level", {}) or {}
    if d_slot:
        k = sorted(d_slot.keys(), key=lambda x: int(x))[0]
        expr = str(d_slot[k])
        return roll_string(expr), expr
    d_char = dmg.get("damage_at_character_level", {}) or {}
    if d_char:
        k = sorted(d_char.keys(), key=lambda x: int(x))[0]
        expr = str(d_char[k])
        return roll_string(expr), expr
    return 0, "0"


def get_save_modifier(personagem, ability: str, calc_mod_fn: Callable[[int], int]) -> int:
    ability = (ability or "").strip().lower()
    mapa = {
        "str": "forca",
        "dex": "destreza",
        "con": "constituicao",
        "int": "inteligencia",
        "wis": "sabedoria",
        "cha": "carisma",
    }
    col = mapa.get(ability)
    if not col:
        return 0
    return calc_mod_fn(int(getattr(personagem, col, 10) or 10))


def clean_name(s: str) -> str:
    return (s or "").strip().strip('"').strip("'").strip()


def spell_fallback(slug_norm: str):
    return SPELL_FALLBACK.get(slug_norm)
