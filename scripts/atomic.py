#!/usr/bin/env python3
"""Атомарная верность (ACCatom, ACL'25 2506.19352) — вторая половина eval-долга.

Проблема (digital-twins research): один score верности ЗАВЫШАЕТ безопасность — многосоставное
заявление помечается «обосновано», если матчнул КУСОК, а необоснованные атомы прячутся.
Решение: разбить на атомы, каждый сверить tier-гейтом (best_match), показать inflation gap =
снисходительный-score − честный атомарный-rate.

Слой дословный (best_match) — детерминированный, здесь. Слой NLI (энтейлмент ПАРАФРАЗА, APC
2405.07726) требует модели и навешивается поверх (faithful-парафраз дословно не матчит).
"""
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.fidelity import best_match

_GROUNDED_TIERS = ("P1", "P2", "S1", "S2")


def atomize(text):
    """Текст → атомарные заявления (предложения/клаузы ≥10 симв.). Нечего бить → [text]."""
    parts = re.split(r"(?<=[.!?;])\s+", text.strip())
    atoms = [p.strip() for p in parts if len(p.strip()) >= 10]
    return atoms or ([text.strip()] if text.strip() else [])


def atomic_grounding(text, advisor_dir):
    """Каждый атом → tier через best_match. Доля обоснованных (P1/P2/S1/S2) = честный rate."""
    atoms = atomize(text)
    per, grounded = [], 0
    for a in atoms:
        m = best_match(a, advisor_dir)
        tier = m[0] if m else None
        ok = tier in _GROUNDED_TIERS
        grounded += ok
        per.append({"atom": a[:60], "tier": tier, "grounded": ok})
    n = len(atoms)
    return {"atoms": n, "grounded": grounded,
            "atom_rate": grounded / n if n else 0.0, "per_atom": per}


def inflation_gap(text, advisor_dir):
    """Завышение единого score: снисходительный (кусок матчнул → «обосновано») минус атомарный.
    inflation>0 = один score врёт в плюс на эту величину."""
    ag = atomic_grounding(text, advisor_dir)
    lenient = 1.0 if ag["grounded"] > 0 else 0.0
    return {"claim_level_lenient": lenient, "atom_level": ag["atom_rate"],
            "inflation": lenient - ag["atom_rate"], "detail": ag}
