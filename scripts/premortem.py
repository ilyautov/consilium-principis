#!/usr/bin/env python3
"""Пре-мортем исхода + леджер sim-vs-real (борроу #3 из MiroFish, с предохранителем).

Прогон сценариев решения вперёд → ожидаемый исход + худший/лучший случай. Ускоряет петлю U1
(не ждать реальный исход месяцами). ПРЕДОХРАНИТЕЛЬ от «predict anything»-театра: прогноз
доверителен лишь настолько, насколько симулятор УЖЕ попадал в реальность. Поэтому:
  • записал прогноз (record_prediction) → позже сверил с фактом (resolve_prediction);
  • simulation_accuracy копит directional-точность + MAE по разрешённым;
  • premortem помечает trustworthy=False, пока нет подтверждённых попаданий.

Сценарии генерит ризонинг (LLM); агрегат и валидация — здесь, детерминированно.
"""


def expected_outcome(scenarios):
    """Сценарии [{label, value, prob}] → ожидаемый исход (веса нормируются) + крайние случаи."""
    total_p = sum(s["prob"] for s in scenarios) or 1.0
    expected = sum(s["value"] * s["prob"] for s in scenarios) / total_p
    worst = min(scenarios, key=lambda s: s["value"])
    best = max(scenarios, key=lambda s: s["value"])
    return {"expected": expected, "worst_case": worst, "best_case": best,
            "verdict": "favorable" if expected > 0 else "unfavorable"}


def record_prediction(ledger, decision_id, predicted):
    """Записать прогноз исхода (число; знак = направление). actual=None до сверки."""
    ledger.append({"decision_id": decision_id, "predicted": predicted, "actual": None})
    return ledger


def resolve_prediction(ledger, decision_id, actual):
    """Сверить прогноз с реальным исходом по факту."""
    for r in ledger:
        if r["decision_id"] == decision_id and r["actual"] is None:
            r["actual"] = actual
            return r
    return None


def simulation_accuracy(ledger):
    """Точность симулятора по РАЗРЕШЁННЫМ прогнозам: directional (совпал ли знак) + MAE."""
    resolved = [r for r in ledger if r["actual"] is not None]
    if not resolved:
        return {"resolved": 0, "directional": None, "mae": None}
    hits = sum(1 for r in resolved if (r["predicted"] >= 0) == (r["actual"] >= 0))
    mae = sum(abs(r["predicted"] - r["actual"]) for r in resolved) / len(resolved)
    return {"resolved": len(resolved), "directional": hits / len(resolved), "mae": mae}


def premortem(scenarios, ledger=None):
    """Ожидаемый исход + доверие к симулятору. trustworthy=False, пока нет подтверждённых
    попаданий (анти-театр: неваидированный прогноз — не основание)."""
    eo = expected_outcome(scenarios)
    trust = simulation_accuracy(ledger) if ledger is not None else {"resolved": 0,
                                                                    "directional": None, "mae": None}
    eo["sim_trust"] = trust
    eo["trustworthy"] = trust["resolved"] > 0
    return eo
