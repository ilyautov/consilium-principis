"""Пре-мортем исхода + леджер sim-vs-real (борроу #3 из MiroFish, с предохранителем).

Прогон сценариев вперёд (ускоряет петлю U1: не ждать реальный исход месяцами). НО прогноз
ценен ровно настолько, насколько симулятор УЖЕ попадал в реальность — иначе это «predict
anything»-театр, который мы раскритиковали. Поэтому ядро несёт леджер: записал прогноз →
позже сверил с фактом → накопил точность. Чистое, детерминированное.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from premortem import (
    expected_outcome, record_prediction, resolve_prediction, simulation_accuracy, premortem,
)

SCEN = [{"label": "оптимизм", "value": 1.0, "prob": 0.3},
        {"label": "вероятный", "value": 0.2, "prob": 0.5},
        {"label": "провал", "value": -0.8, "prob": 0.2}]


def test_expected_outcome_weighted_mean():
    eo = expected_outcome(SCEN)
    assert abs(eo["expected"] - 0.24) < 1e-9          # 0.3 + 0.1 − 0.16
    assert eo["worst_case"]["label"] == "провал"
    assert eo["best_case"]["label"] == "оптимизм"
    assert eo["verdict"] == "favorable"


def test_expected_outcome_normalizes_probs():
    eo = expected_outcome([{"label": "a", "value": 1.0, "prob": 2},
                           {"label": "b", "value": 0.0, "prob": 2}])
    assert abs(eo["expected"] - 0.5) < 1e-9           # веса нормируются


def test_ledger_record_resolve_and_accuracy():
    led = []
    record_prediction(led, "d1", 0.5)
    record_prediction(led, "d2", 0.4)
    resolve_prediction(led, "d1", 0.8)                # тот же знак → попал
    resolve_prediction(led, "d2", -0.3)               # знак разошёлся → мимо
    acc = simulation_accuracy(led)
    assert acc["resolved"] == 2
    assert acc["directional"] == 0.5                  # 1 из 2 по направлению
    assert acc["mae"] is not None


def test_accuracy_none_when_unresolved():
    led = []
    record_prediction(led, "d1", 0.5)
    acc = simulation_accuracy(led)
    assert acc["resolved"] == 0 and acc["directional"] is None


def test_premortem_without_validation_flags_untrusted():
    # пре-мортем без истории попаданий → НЕ доверять (анти-театр)
    res = premortem(SCEN, ledger=[])
    assert res["sim_trust"]["resolved"] == 0
    assert res["trustworthy"] is False


def test_premortem_with_history_carries_trust():
    led = []
    record_prediction(led, "p", 0.5); resolve_prediction(led, "p", 0.6)
    res = premortem(SCEN, ledger=led)
    assert res["sim_trust"]["resolved"] == 1
    assert res["trustworthy"] is True                 # есть подтверждённое попадание
