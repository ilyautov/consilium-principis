"""Доверие через стабильность — вердикт держится при повторных прогонах или это монетка?

Анти-театр: красивый одиночный вывод может быть случайностью. Гоняем карту/совет N раз,
меряем согласие. Robust ≠ coin-flip, наряженный в мудрость. Ядро чистое (список вердиктов).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from stability import stability, confidence_label


def test_unanimous_is_robust():
    s = stability(["winnable", "winnable", "winnable"])
    assert s["modal"] == "winnable" and s["agreement"] == 1.0
    assert s["stable"] is True and s["label"] == "robust"


def test_majority_is_leaning():
    s = stability(["winnable", "winnable", "no_winning_line"])
    assert s["modal"] == "winnable"
    assert abs(s["agreement"] - 2 / 3) < 1e-9
    assert s["label"] == "leaning"


def test_split_is_coin_flip():
    s = stability(["a", "b", "c"])
    assert s["agreement"] < 0.5
    assert s["stable"] is False and s["label"] == "coin-flip"


def test_confidence_label_thresholds():
    assert confidence_label(1.0) == "robust"
    assert confidence_label(0.7) == "leaning"
    assert confidence_label(0.4) == "coin-flip"


def test_empty_is_coin_flip():
    s = stability([])
    assert s["agreement"] == 0.0 and s["label"] == "coin-flip"
