#!/usr/bin/env python3
"""Детерминированное Монте-Карло-ядро карты решения («Principis-расчёт», спека §3).

Ноль LLM в счёте: LLM элицитирует модель, считает ТОЛЬКО этот код — stdlib
random.Random(seed), без numpy, без сети. Тот же сид → результат байт-в-байт
(тестируемый инвариант: json.dumps sort_keys).

Схема расчёта:
  • fail-closed: карта прогоняется через validate_map ПРЯМО ЗДЕСЬ — невалидная
    карта не считается, даже если вызывающий код забыл проверить;
  • на сценарий каждая неопределённость сэмплируется ОДИН раз (continuous →
    треугольное random.triangular(min, max, mode); event → Бернулли prob) и
    подставляется во ВСЕ варианты — иначе попарное сравнение нечестное;
  • direction=min инвертирует «лучше» ВЕЗДЕ (пары, лучший, regret) — честно,
    а не знаком.

Выход (спека §3): на вариант mean/median/p10/p90; попарно P(A лучше B);
P(вариант лучший); expected regret (упущенное против лучшего в каждом сценарии);
торнадо; label — данные «📐 рамки» для Ф2.

Решения (задокументированы, ревью Ф1):
  • Деление на ноль в ЛЮБОМ сценарии → падает ВЕСЬ расчёт (fail-closed):
    формула, делящаяся на ноль внутри подтверждённых диапазонов, — дефект
    модели; молча выкидывать сценарии = врать о распределении.
  • Торнадо — ОДИН метод: impact = |корреляция Пирсона| сэмплов величины с
    исходом ЛУЧШЕГО варианта каждого сценария (то, что юзер реально получает,
    выбирая оптимально). Детерминирован, без повторных прогонов; нулевая
    дисперсия → вклад 0.0. top_uncertainties — top-2 по вкладу (оси 2×2, §4).
  • Ничьи: P(A лучше B) считает ничью за 0.5 (P(A>B)+P(B>A)=1);
    «лучший» при ничьей делится поровну между совпавшими (Σ P(best) = 1).
  • Перцентили — линейная интерполяция по отсортированным сэмплам
    (медиана = перцентиль 0.5, при чётном n совпадает с классической).
  • seed — только int (bool отвергается): воспроизводимость между запусками.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from decision_map import KIND_EVENT, DIRECTION_MIN, validate_map
from safe_expr import SafeExprEvalError, compile_expr

N_DEFAULT = 10_000


def _percentile(sorted_vals, q):
    """Перцентиль с линейной интерполяцией (детерминирован, без numpy)."""
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] + (sorted_vals[lo + 1] - sorted_vals[lo]) * frac
    return sorted_vals[lo]


def _pearson(xs, ys):
    """|Корреляция Пирсона|; нулевая дисперсия любой из сторон → 0.0 (не NaN)."""
    n = len(xs)
    mx = math.fsum(xs) / n
    my = math.fsum(ys) / n
    cov = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.fsum((x - mx) ** 2 for x in xs)
    vy = math.fsum((y - my) ** 2 for y in ys)
    if vx == 0.0 or vy == 0.0:
        return 0.0
    return abs(cov / math.sqrt(vx * vy))


def mc_run(m, seed, n=N_DEFAULT):
    """Прогоняет валидную карту решения n раз с сидом → dict результата (спека §3).

    Fail-closed: невалидная карта, нечисловые seed/n, деление на ноль в формуле →
    ValueError с RU-текстом, никаких частичных чисел.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("Сид расчёта должен быть целым числом — получено: %r." % (seed,))
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("Число сценариев n должно быть целым >= 1 — получено: %r." % (n,))

    errors = validate_map(m)
    if errors:
        raise ValueError(
            "Карта решения не проходит гейты честности — расчёт не запущен "
            "(fail-closed):\n- " + "\n- ".join(errors))

    uncertainties = m["uncertainties"]
    option_ids = [o["id"] for o in m["options"]]
    allowed = {u["id"] for u in uncertainties}
    evaluators = {oid: compile_expr(m["model"][oid]["expr"], allowed)
                  for oid in option_ids}
    is_min = m["stakes"]["direction"] == DIRECTION_MIN

    # сэмплы: величина → список по сценариям; вариант → список исходов
    rng = random.Random(seed)
    u_samples = {u["id"]: [] for u in uncertainties}
    o_values = {oid: [] for oid in option_ids}
    best_values = []                       # исход лучшего варианта на сценарий
    win_share = {oid: 0.0 for oid in option_ids}
    regret_sum = {oid: 0.0 for oid in option_ids}
    pair_wins = {a: {b: 0.0 for b in option_ids if b != a} for a in option_ids}

    for _ in range(n):
        env = {}
        for u in uncertainties:            # порядок карты — часть детерминизма
            if u["kind"] == KIND_EVENT:
                val = 1.0 if rng.random() < u["prob"] else 0.0
            else:
                val = rng.triangular(u["min"], u["max"], u["mode"])
            env[u["id"]] = val
            u_samples[u["id"]].append(val)

        try:                               # ОДИН env на все варианты — честное сравнение
            values = {oid: evaluators[oid](env) for oid in option_ids}
        except SafeExprEvalError as e:
            raise ValueError("Расчёт остановлен (fail-closed): %s" % e)

        best = min(values.values()) if is_min else max(values.values())
        best_values.append(best)
        winners = [oid for oid in option_ids if values[oid] == best]
        for oid in winners:
            win_share[oid] += 1.0 / len(winners)
        for oid in option_ids:
            o_values[oid].append(values[oid])
            regret_sum[oid] += (values[oid] - best) if is_min else (best - values[oid])
        for a in option_ids:
            for b in pair_wins[a]:
                va, vb = values[a], values[b]
                if va == vb:
                    pair_wins[a][b] += 0.5
                elif (va < vb) if is_min else (va > vb):
                    pair_wins[a][b] += 1.0

    options_out = {}
    for oid in option_ids:
        vals = sorted(o_values[oid])
        options_out[oid] = {
            "mean": math.fsum(vals) / n,
            "median": _percentile(vals, 0.5),
            "p10": _percentile(vals, 0.10),
            "p90": _percentile(vals, 0.90),
        }

    # торнадо: |corr(сэмплы величины, исход лучшего варианта сценария)|;
    # сортировка по вкладу, при равенстве — порядок величин в карте (stable sort)
    tornado = [{"id": u["id"], "impact": _pearson(u_samples[u["id"]], best_values)}
               for u in uncertainties]
    tornado.sort(key=lambda t: -t["impact"])

    return {
        "options": options_out,
        "pairwise": {a: {b: pair_wins[a][b] / n for b in pair_wins[a]}
                     for a in option_ids},
        "p_best": {oid: win_share[oid] / n for oid in option_ids},
        "expected_regret": {oid: regret_sum[oid] / n for oid in option_ids},
        "tornado": tornado,
        "top_uncertainties": [t["id"] for t in tornado[:2]],
        # «📐 рамка» (Ф2): модель юзера — K величин, подтверждены им, сид S, n прогонов
        "label": {"n_uncertainties": len(uncertainties), "seed": seed, "n": n,
                  "confirmed": True},
    }
