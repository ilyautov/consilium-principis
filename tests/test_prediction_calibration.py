"""Числовая калибровка прогнозов (§2.4) — Brier/log для событий, MAE + покрытие
интервала для величин, журнал по группам kind+unit. Ноль LLM, ноль сети.

Это НЕ калибровка подачи (light/dark, calibration.py) — это точность ПРОГНОЗОВ:
сравнивает сохранённые в Card числа (probability / p10-p50-p90) с фактом (occurred /
actual). Порог показа — по аналогии с premortem.trustworthy (шумно при малом N).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import prediction_calibration as pc  # noqa: E402


def _event_card(cid, p, occurred, unit=None):
    pred = {"id": "p_" + cid, "kind": "event", "statement": "x",
            "probability": p, "horizon_days": 30}
    return {"id": "dc_" + cid, "kind": "decision_card",
            "prediction": pred,
            "outcome": {"resolved_on": "2026-01-01", "occurred": occurred}}


def _metric_card(cid, p50, actual, p10=None, p90=None, unit="ед"):
    pred = {"id": "p_" + cid, "kind": "metric", "statement": "x", "unit": unit,
            "p10": p10 if p10 is not None else p50 - 10,
            "p50": p50, "p90": p90 if p90 is not None else p50 + 10,
            "direction": "max", "horizon_days": 30}
    return {"id": "dc_" + cid, "kind": "decision_card",
            "prediction": pred,
            "outcome": {"resolved_on": "2026-01-01", "actual": actual}}


# ── Brier / log score (события) ─────────────────────────────────────────────

def test_brier_perfect_confident_correct_is_zero():
    # p=1, y=1 → (1-1)^2 = 0
    r = pc.brier([_event_card("a", 1.0, True)])
    assert r["brier"] == 0.0 and r["n"] == 1


def test_brier_confident_wrong_is_one():
    # p=0, y=1 → (0-1)^2 = 1
    assert pc.brier([_event_card("a", 0.0, True)])["brier"] == 1.0


def test_brier_mean_over_cards():
    # (1-1)^2=0 и (0-1)^2=1 → среднее 0.5
    cards = [_event_card("a", 1.0, True), _event_card("b", 0.0, True)]
    assert pc.brier(cards)["brier"] == 0.5


def test_log_score_confident_wrong_is_clipped_not_inf():
    # p=0, y=1 → −ln(0) = ∞; клип на ε спасает от бесконечности
    r = pc.log_score([_event_card("a", 0.0, True)])
    assert math.isfinite(r["log_score"]) and r["log_score"] > 0


def test_log_score_perfect_is_near_zero():
    r = pc.log_score([_event_card("a", 1.0, True)])
    assert r["log_score"] < 1e-6


def test_brier_ignores_metric_cards():
    assert pc.brier([_metric_card("m", 100, 100)])["n"] == 0


# ── MAE / покрытие интервала (величины) ─────────────────────────────────────

def test_mae_absolute_error_of_p50():
    # |130 - 105| = 25
    assert pc.mae([_metric_card("a", 105, 130)])["mae"] == 25.0


def test_mae_mean_over_cards():
    cards = [_metric_card("a", 100, 110), _metric_card("b", 100, 90)]  # |10|,|10| → 10
    assert pc.mae(cards)["mae"] == 10.0


def test_interval_coverage_fraction_inside():
    # 3 из 4 внутри [p10,p90] → 0.75
    cards = [
        _metric_card("a", 100, 105, p10=90, p90=110),   # внутри
        _metric_card("b", 100, 95, p10=90, p90=110),    # внутри
        _metric_card("c", 100, 108, p10=90, p90=110),   # внутри
        _metric_card("d", 100, 200, p10=90, p90=110),   # снаружи
    ]
    assert pc.interval_coverage(cards)["coverage"] == 0.75


def test_coverage_boundary_inclusive():
    # actual ровно на p90 → считается покрытым
    assert pc.interval_coverage([_metric_card("a", 100, 110, p10=90, p90=110)])["coverage"] == 1.0


def test_mae_ignores_event_cards():
    assert pc.mae([_event_card("e", 0.5, True)])["n"] == 0


# ── журнал по группам kind+unit ─────────────────────────────────────────────

def test_journal_groups_by_kind_and_unit():
    cards = [
        _metric_card("a", 100, 110, unit="рубли"),
        _metric_card("b", 100, 90, unit="рубли"),
        _metric_card("c", 5, 6, unit="штуки"),
        _event_card("e", 0.8, True),
    ]
    j = pc.calibration_journal(cards)
    groups = j["groups"]
    keys = {g["key"] for g in groups}
    assert "metric:рубли" in keys and "metric:штуки" in keys and "event" in keys


def test_journal_group_carries_right_metrics():
    cards = [_metric_card("a", 100, 110, unit="рубли"),
             _metric_card("b", 100, 90, unit="рубли")]
    j = pc.calibration_journal(cards)
    g = next(g for g in j["groups"] if g["key"] == "metric:рубли")
    assert g["n"] == 2 and g["mae"] == 10.0 and "coverage" in g


def test_journal_event_group_has_brier_and_log():
    cards = [_event_card("a", 1.0, True), _event_card("b", 0.0, False)]
    j = pc.calibration_journal(cards)
    g = next(g for g in j["groups"] if g["key"] == "event")
    assert "brier" in g and "log_score" in g


def test_journal_marks_trustworthy_by_threshold():
    # < порога закрытых → trustworthy=False (шумно, прячем как premortem)
    few = [_event_card(str(i), 0.5, True) for i in range(pc.MIN_TRUSTWORTHY_N - 1)]
    g_few = pc.calibration_journal(few)["groups"][0]
    assert g_few["trustworthy"] is False
    many = [_event_card(str(i), 0.5, True) for i in range(pc.MIN_TRUSTWORTHY_N)]
    g_many = pc.calibration_journal(many)["groups"][0]
    assert g_many["trustworthy"] is True


def test_journal_ignores_open_cards():
    open_card = {"id": "dc_open", "kind": "decision_card",
                 "prediction": {"id": "p", "kind": "event", "statement": "x",
                                "probability": 0.5, "horizon_days": 30},
                 "outcome": None}
    j = pc.calibration_journal([open_card])
    assert j["groups"] == [] and j["closed"] == 0


def test_empty_input_is_quiet():
    j = pc.calibration_journal([])
    assert j["closed"] == 0 and j["groups"] == []
