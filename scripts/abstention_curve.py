#!/usr/bin/env python3
"""Кривая abstention ↔ ложный-отказ — честная замена headline-проценту.

Проблема (digital-twins research, 2026-06-26): «честных отказов 100%» как ОДНО число
ЗАВЫШАЕТ безопасность, потому что прячет цену — ложные отказы на in-corpus вопросах.
Поднимаешь порог → растёт честный-отказ на OOC, НО заодно режешь отвечаемые вопросы.
Правильная картина — кривая trade-off по порогу + рабочая точка (Youden-knee) + AUC.

Математика кривой ЧИСТАЯ: на вход — уже посчитанные max-скоры ретрива для двух наборов
(OOC = «должны отказать», answerable = «должны ответить»). Сбор скоров — в eval.py
(нужен корпус/движок); здесь — только математика, поэтому детерминированно тестируется.
"""


def curve_from_scores(ooc_scores, ans_scores, thresholds):
    """Для каждого порога t: доля честных отказов (OOC<t) и ложных отказов (answerable<t).

    youden = honest_abstain - false_abstain ∈ [-1,1] — чистый выигрыш порога (J-статистика).
    """
    points = []
    for t in thresholds:
        honest = _frac_below(ooc_scores, t)        # OOC < t → корректный отказ
        false_ab = _frac_below(ans_scores, t)      # answerable < t → ЛОЖНЫЙ отказ
        points.append({
            "threshold": t,
            "honest_abstain": honest,
            "false_abstain": false_ab,
            "youden": honest - false_ab,
        })
    return points


def _frac_below(scores, t):
    if not scores:
        return 0.0
    return sum(1 for s in scores if s < t) / len(scores)


def best_operating_point(points):
    """Рабочая точка = max youden. Тай-брейк: ниже false_abstain, затем ниже порог
    (меньше калечит in-corpus). None, если точек нет."""
    if not points:
        return None
    return min(points, key=lambda p: (-p["youden"], p["false_abstain"], p["threshold"]))


def thresholds_from_scores(scores, n=21):
    """n порогов, равномерно покрывающих наблюдаемый диапазон скоров (работает для любого
    бэкенда: semantic ~[0,1], lexical ~[0,0.1]). Вырожденный случай (все равны) → один порог."""
    if not scores:
        return [0.5]
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-12:
        return [lo]
    n = max(2, n)
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


def curve_auc(ooc_scores, ans_scores):
    """AUC разделимости: вероятность, что случайный OOC-скор НИЖЕ случайного answerable-скора
    (= насколько порог в принципе способен развести наборы). 1.0 — идеал, 0.5 — неразличимы.
    Эквивалент Манна-Уитни (ничьи считаем за 0.5)."""
    if not ooc_scores or not ans_scores:
        return 0.0
    wins = 0.0
    for o in ooc_scores:
        for a in ans_scores:
            if o < a:
                wins += 1.0
            elif o == a:
                wins += 0.5
    return wins / (len(ooc_scores) * len(ans_scores))
