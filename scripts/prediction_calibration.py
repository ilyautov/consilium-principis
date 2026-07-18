#!/usr/bin/env python3
"""Числовая калибровка ПРОГНОЗОВ (decision-lifecycle §2.4).

НЕ путать с calibration.py — та калибрует ПОДАЧУ (light/dark) по одобрению исходов. Здесь
меряется ТОЧНОСТЬ прогнозов: сохранённые в Card числа (probability / p10-p50-p90) против
факта (occurred / actual).

  • События (event): Brier score mean((p−y)^2) и log score mean(−[y·ln p+(1−y)·ln(1−p)])
    с клипом p∈[ε,1−ε] (иначе ln 0 = −∞). Меньше — лучше.
  • Величины (metric): MAE mean(|actual−p50|); покрытие интервала — доля закрытых, где
    p10 <= actual <= p90 (цель ≈ 0.80 при честных p10/p90); bias mean(actual−p50).
  • Журнал: агрегаты по группе СОПОСТАВИМЫХ решений — v1: kind+unit («яблоки с яблоками»).

Порог показа (§8.7): при малом N Brier/MAE шумны — trustworthy=False до MIN_TRUSTWORTHY_N
закрытых (по аналогии с premortem.trustworthy, но с числовым порогом вместо resolved>0).
Ноль LLM, ноль сети — чистые функции от списка закрытых Card.
"""
import math

# Порог «журнал набрал вес» (§8.7): ниже — метрики показываем, но помечаем как шумные.
MIN_TRUSTWORTHY_N = 5

_EPS = 1e-9   # клип вероятности во избежание ln(0) в log score


def _closed(cards, kind=None):
    """Закрытые Card (outcome есть) нужного вида прогноза."""
    out = []
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        pred = c.get("prediction")
        outcome = c.get("outcome")
        if not isinstance(pred, dict) or not isinstance(outcome, dict):
            continue
        if kind is not None and pred.get("kind") != kind:
            continue
        out.append((pred, outcome))
    return out


# ── события ──────────────────────────────────────────────────────────────────

def brier(cards):
    """Brier score по event-Card: mean((p − y)^2), y∈{0,1}. Меньше — лучше."""
    pairs = _closed(cards, "event")
    if not pairs:
        return {"n": 0, "brier": None}
    s = math.fsum((pred["probability"] - (1.0 if outcome["occurred"] else 0.0)) ** 2
                  for pred, outcome in pairs)
    return {"n": len(pairs), "brier": s / len(pairs)}


def log_score(cards):
    """Log score по event-Card: mean(−[y·ln p + (1−y)·ln(1−p)]), p клипается в [ε,1−ε]."""
    pairs = _closed(cards, "event")
    if not pairs:
        return {"n": 0, "log_score": None}
    total = 0.0
    for pred, outcome in pairs:
        p = min(max(pred["probability"], _EPS), 1.0 - _EPS)
        y = 1.0 if outcome["occurred"] else 0.0
        total += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
    return {"n": len(pairs), "log_score": total / len(pairs)}


# ── величины ─────────────────────────────────────────────────────────────────

def mae(cards):
    """MAE по metric-Card: mean(|actual − p50|)."""
    pairs = _closed(cards, "metric")
    if not pairs:
        return {"n": 0, "mae": None}
    s = math.fsum(abs(outcome["actual"] - pred["p50"]) for pred, outcome in pairs)
    return {"n": len(pairs), "mae": s / len(pairs)}


def interval_coverage(cards):
    """Покрытие интервала: доля metric-Card, где p10 <= actual <= p90 (границы включительно)."""
    pairs = _closed(cards, "metric")
    if not pairs:
        return {"n": 0, "coverage": None}
    inside = sum(1 for pred, outcome in pairs
                 if pred["p10"] <= outcome["actual"] <= pred["p90"])
    return {"n": len(pairs), "coverage": inside / len(pairs)}


def bias(cards):
    """Систематический сдвиг metric-прогноза: mean(actual − p50) (>0 — недооценка p50)."""
    pairs = _closed(cards, "metric")
    if not pairs:
        return {"n": 0, "bias": None}
    s = math.fsum(outcome["actual"] - pred["p50"] for pred, outcome in pairs)
    return {"n": len(pairs), "bias": s / len(pairs)}


# ── журнал по сопоставимым группам ───────────────────────────────────────────

def comparability_key(pred):
    """Ключ сопоставимости (§2.4): v1 = kind (+ unit для metric). Вынесен отдельно —
    расширяемо (домен/владелец) позже без правки метрик."""
    kind = pred.get("kind")
    if kind == "metric":
        return "metric:%s" % (pred.get("unit") or "?")
    return "event"


def calibration_journal(cards, min_n=MIN_TRUSTWORTHY_N):
    """Числовая калибровка по группам сопоставимых решений.

    → {"closed": int, "groups": [{"key", "kind", "unit"|None, "n", "trustworthy",
       event: "brier","log_score" | metric: "mae","coverage","bias"}]}.
    Открытые Card (outcome=None) игнорируются. Группы сортируются по ключу (детерминизм)."""
    buckets = {}
    for pred, outcome in _closed(cards):
        buckets.setdefault(comparability_key(pred), []).append({"prediction": pred,
                                                                "outcome": outcome})
    groups = []
    for key in sorted(buckets):
        grp_cards = buckets[key]
        n = len(grp_cards)
        kind = grp_cards[0]["prediction"].get("kind")
        g = {"key": key, "kind": kind, "n": n, "trustworthy": n >= min_n}
        if kind == "event":
            g["brier"] = brier(grp_cards)["brier"]
            g["log_score"] = log_score(grp_cards)["log_score"]
            g["unit"] = None
        else:
            g["mae"] = mae(grp_cards)["mae"]
            g["coverage"] = interval_coverage(grp_cards)["coverage"]
            g["bias"] = bias(grp_cards)["bias"]
            g["unit"] = grp_cards[0]["prediction"].get("unit")
        groups.append(g)
    return {"closed": len(_closed(cards)), "groups": groups}
