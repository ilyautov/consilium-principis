"""Атомарная верность (ACCatom, ACL'25) — вторая половина eval-долга из digital-twins research.

Один score верности ЗАВЫШАЕТ: многосоставное заявление помечается «обосновано», если матчнул
кусок, а необоснованные атомы прячутся. Разбиваем на атомы, каждый сверяем гейтом, считаем
inflation gap = снисходительный-score − атомарный-rate. Дословный слой детерминирован (best_match);
NLI-слой (энтейлмент парафраза, APC) — модельное расширение поверх.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from atomic import atomize, atomic_grounding, inflation_gap

STRAT = os.path.join(ROOT, "lenses", "strategist")


def test_atomize_splits_into_claims():
    a = atomize("All warfare is based on deception. Сунь-цзы любил мороженое.")
    assert len(a) == 2
    assert a[0].startswith("All warfare")


def test_atomize_single_claim_stays_whole():
    assert atomize("All warfare is based on deception.") == ["All warfare is based on deception."]


def test_single_canon_maxim_fully_grounded():
    ag = atomic_grounding("All warfare is based on deception.", STRAT)
    assert ag["atoms"] == 1 and ag["grounded"] == 1
    assert ag["atom_rate"] == 1.0


def test_compound_reveals_partial_grounding():
    # один атом — канон (🔵), второй — выдумка → атомарно 1/2, хотя «что-то матчнуло»
    text = "All warfare is based on deception. Сунь-цзы обожал мороженое по воскресеньям."
    ag = atomic_grounding(text, STRAT)
    assert ag["atoms"] == 2 and ag["grounded"] == 1
    assert ag["atom_rate"] == 0.5


def test_inflation_gap_exposes_single_score_lie():
    text = "All warfare is based on deception. Сунь-цзы обожал мороженое по воскресеньям."
    g = inflation_gap(text, STRAT)
    assert g["claim_level_lenient"] == 1.0      # «кусок матчнул → обосновано»
    assert g["atom_level"] == 0.5               # честная атомарная доля
    assert abs(g["inflation"] - 0.5) < 1e-9     # завышение на 0.5


def test_fully_fabricated_no_false_grounding():
    g = inflation_gap("Сунь-цзы родился в Бостоне. Он играл в бейсбол.", STRAT)
    assert g["atom_level"] == 0.0
    assert g["inflation"] == 0.0                # ничего не помечено обоснованным ложно
