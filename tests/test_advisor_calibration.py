"""Калибровка советника по ИСХОДУ — кто из совета реально был прав ДЛЯ ТЕБЯ → вес голоса.

Петля U1: track_record сейчас только СЧИТАЕТ resolved/pending. Это не делает совет умнее —
вес всех голосов равен вечно. Здесь: советник, чьи советы вели к ОДОБРЕННЫМ хорошим исходам,
получает больший вес. Laplace-сглаживание: без данных вес нейтрален (0.5), не 0. Ядро чистое.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from advisor_calibration import advisor_scores, vote_weights


RECS = [
    {"advisor": "machiavelli", "outcome": "good", "endorsed": True},
    {"advisor": "machiavelli", "outcome": "good", "endorsed": True},
    {"advisor": "marcus-aurelius", "outcome": "bad", "endorsed": False},
    {"advisor": "marcus-aurelius", "outcome": "bad", "endorsed": False},
    {"advisor": "machiavelli", "outcome": "pending", "endorsed": None},   # не resolved
]


def test_advisor_score_rewards_endorsed_good_outcomes():
    s = advisor_scores(RECS)
    assert s["machiavelli"]["resolved"] == 2 and s["machiavelli"]["hits"] == 2
    assert abs(s["machiavelli"]["score"] - 0.75) < 1e-9      # (2+1)/(2+2) Laplace
    assert abs(s["marcus-aurelius"]["score"] - 0.25) < 1e-9  # (0+1)/(2+2)


def test_pending_excluded_from_resolved():
    s = advisor_scores(RECS)
    assert s["machiavelli"]["n"] == 3 and s["machiavelli"]["resolved"] == 2


def test_no_data_advisor_is_neutral_not_zero():
    s = advisor_scores([{"advisor": "naval", "outcome": "pending", "endorsed": None}])
    assert s["naval"]["resolved"] == 0
    assert abs(s["naval"]["score"] - 0.5) < 1e-9             # нейтральный приор, не 0


def test_vote_weights_normalized_and_ordered():
    w = vote_weights(RECS)
    assert abs(sum(w.values()) - 1.0) < 1e-9                 # нормированы
    assert w["machiavelli"] > w["marcus-aurelius"]          # кто был прав — весит больше


def test_empty_gives_empty():
    assert advisor_scores([]) == {} and vote_weights([]) == {}
