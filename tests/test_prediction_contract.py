"""Prediction contract — числа берутся ПРЯМО из mc_run и хранятся ЧИСЛАМИ (§2.2).

Закрывает разрыв §1.2: сегодня p10/p50/p90 из mc_run схлопываются в RU-строку и
воскрешаются регексом без чисел. build_prediction_from_mc держит их числами:
event ← p_best[chosen]; metric ← options[chosen].{p10,median,p90}, unit ← stakes.metric,
direction ← stakes.direction. Ноль LLM, ноль сети (mc_run детерминирован).
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import decision_card as dc  # noqa: E402
from mc_run import mc_run  # noqa: E402


def _valid_map():
    return {
        "question": "Куда вкладывать месяц?",
        "options": [
            {"id": "ship_public", "name": "Выпустить", "reversibility": "one-way"},
            {"id": "status_quo", "name": "Ничего", "reversibility": "two-way",
             "status_quo": True},
        ],
        "uncertainties": [
            {"id": "traction_prob", "kind": "event", "prob": 0.3, "confirmed_by_user": True},
            {"id": "hours_to_ship", "kind": "continuous", "min": 20, "mode": 40, "max": 90,
             "confirmed_by_user": True},
            {"id": "upside_hours", "kind": "continuous", "min": 50, "mode": 150, "max": 400,
             "confirmed_by_user": True},
        ],
        "stakes": {"metric": "ценность в часах", "direction": "max"},
        "horizon": "3 месяца",
        "model": {
            "ship_public": {"expr": "traction_prob * upside_hours - hours_to_ship",
                            "words": "трекшн × апсайд − часы"},
            "status_quo": {"expr": "0", "words": "ноль"},
        },
    }


@pytest.fixture
def mc():
    return mc_run(_valid_map(), seed=2026, n=2000)


def test_metric_prediction_copies_numbers_from_mc(mc):
    m = _valid_map()
    pred = dc.build_prediction_from_mc(m, mc, "ship_public", form="metric",
                                       horizon_days=90, created="2026-07-18")
    assert pred["kind"] == "metric"
    assert pred["p10"] == mc["options"]["ship_public"]["p10"]
    assert pred["p50"] == mc["options"]["ship_public"]["median"]
    assert pred["p90"] == mc["options"]["ship_public"]["p90"]
    # числа хранятся ЧИСЛАМИ, не строкой
    assert all(isinstance(pred[k], (int, float)) for k in ("p10", "p50", "p90"))


def test_metric_prediction_unit_and_direction_from_stakes(mc):
    m = _valid_map()
    pred = dc.build_prediction_from_mc(m, mc, "ship_public", form="metric", horizon_days=90)
    assert pred["unit"] == "ценность в часах"
    assert pred["direction"] == "max"


def test_event_prediction_probability_from_p_best(mc):
    m = _valid_map()
    pred = dc.build_prediction_from_mc(m, mc, "ship_public", form="event", horizon_days=90)
    assert pred["kind"] == "event"
    assert pred["probability"] == mc["p_best"]["ship_public"]
    assert 0.0 <= pred["probability"] <= 1.0


def test_prediction_from_mc_passes_card_gates(mc):
    m = _valid_map()
    pred = dc.build_prediction_from_mc(m, mc, "ship_public", form="metric",
                                       horizon_days=90, created="2026-07-18")
    # собранный прогноз должен проходить те же гейты, что и вручную написанный
    assert dc.validate_prediction(pred) == []


def test_resolves_on_derived_from_created_and_horizon(mc):
    m = _valid_map()
    pred = dc.build_prediction_from_mc(m, mc, "ship_public", form="event",
                                       horizon_days=90, created="2026-07-18")
    assert pred["resolves_on"] == "2026-10-16"     # 2026-07-18 + 90 дней


def test_unknown_option_rejected(mc):
    m = _valid_map()
    with pytest.raises(ValueError):
        dc.build_prediction_from_mc(m, mc, "no_such_option", form="metric", horizon_days=90)


def test_form_auto_defaults_to_metric_when_unit_present(mc):
    m = _valid_map()
    pred = dc.build_prediction_from_mc(m, mc, "ship_public", horizon_days=90)
    assert pred["kind"] == "metric"      # D-развилка: metric по умолчанию, когда есть единицы
