#!/usr/bin/env python3
"""Доверие через стабильность — держится ли вердикт при повторных прогонах (анти-театр).

Одиночный красивый вывод может быть случайностью (стохастика генерации). Гоняем карту/совет
N раз, меряем согласие = доля прогонов с модальным вердиктом. robust ≠ coin-flip в мудрой
обёртке. Чистое ядро над списком вердиктов (категориальные строки).
"""
from collections import Counter

_ROBUST, _LEANING = 0.8, 0.6


def confidence_label(agreement):
    if agreement >= _ROBUST:
        return "robust"
    if agreement >= _LEANING:
        return "leaning"
    return "coin-flip"


def stability(verdicts):
    """[вердикт, …] → {n, modal, agreement, stable, label}. agreement = доля модального."""
    n = len(verdicts)
    if not n:
        return {"n": 0, "modal": None, "agreement": 0.0, "stable": False, "label": "coin-flip"}
    modal, count = Counter(verdicts).most_common(1)[0]
    agreement = count / n
    label = confidence_label(agreement)
    return {"n": n, "modal": modal, "agreement": agreement,
            "stable": label == "robust", "label": label}
