"""Детерминированное МК-ядро — тесты mc_run (спека §3).

Инварианты:
  • ДЕТЕРМИНИЗМ: тот же сид → результат байт-в-байт (json.dumps sort_keys);
    другой сид → другой результат. Ноль LLM, ноль сети — stdlib random.Random.
  • ЧЕСТНОЕ СРАВНЕНИЕ: неопределённости сэмплируются ОДИН раз на сценарий,
    подставляются во ВСЕ варианты.
  • Статистическая вменяемость: треугольное mean ≈ (min+mode+max)/3 на 50k;
    событие ≈ prob; P(A>B)=1.0 при доминировании; regret >= 0.
  • direction=min честно инвертирует сравнения (победитель меняется).
  • Торнадо находит реально доминирующую величину.
  • FAIL-CLOSED: невалидная карта / деление на ноль → расчёт не выдаёт чисел.
"""
import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mc_run import mc_run


def _cont(uid, lo, mode, hi):
    return {"id": uid, "kind": "continuous", "min": lo, "mode": mode, "max": hi,
            "confirmed_by_user": True, "elicited": "…"}


def _event(uid, prob):
    return {"id": uid, "kind": "event", "prob": prob,
            "confirmed_by_user": True, "elicited": "…"}


def _map(uncertainties, model, direction="max"):
    """Карта с двумя вариантами a/b (b — статус-кво)."""
    return {
        "question": "тестовое решение",
        "options": [
            {"id": "a", "name": "Вариант А"},
            {"id": "b", "name": "Статус-кво", "status_quo": True},
        ],
        "uncertainties": uncertainties,
        "stakes": {"metric": "часы", "direction": direction},
        "horizon": "месяц",
        "model": {k: {"expr": v, "words": "словесная версия «%s»" % v}
                  for k, v in model.items()},
    }


def _spec_map():
    """Карта из спеки §1."""
    return {
        "question": "куда вкладывать месяц",
        "options": [
            {"id": "ship_public", "name": "Шипнуть"},
            {"id": "status_quo", "name": "Ничего", "status_quo": True},
        ],
        "uncertainties": [
            _event("traction_prob", 0.3),
            _cont("hours_to_ship", 20, 40, 90),
            _cont("upside_hours", 50, 150, 400),
        ],
        "stakes": {"metric": "часы", "direction": "max"},
        "horizon": "3 месяца",
        "model": {
            "ship_public": {"expr": "traction_prob * upside_hours - hours_to_ship",
                            "words": "P(трекшен) на выигрыш минус затраты"},
            "status_quo": {"expr": "0", "words": "ноль"},
        },
    }


# ── детерминизм ─────────────────────────────────────────────────────────────

def test_same_seed_byte_identical():
    r1 = mc_run(_spec_map(), seed=42, n=2000)
    r2 = mc_run(_spec_map(), seed=42, n=2000)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_different_seed_differs():
    r1 = mc_run(_spec_map(), seed=42, n=2000)
    r2 = mc_run(_spec_map(), seed=43, n=2000)
    assert json.dumps(r1, sort_keys=True) != json.dumps(r2, sort_keys=True)


def test_input_map_not_mutated():
    m = _spec_map()
    snapshot = copy.deepcopy(m)
    mc_run(m, seed=1, n=100)
    assert m == snapshot


def test_result_json_serializable():
    json.dumps(mc_run(_spec_map(), seed=7, n=500))


# ── статистическая вменяемость ──────────────────────────────────────────────

def test_triangular_mean_sanity():
    # mean треугольного = (min + mode + max) / 3 = (20+40+90)/3 = 50
    m = _map([_cont("x", 20, 40, 90)], {"a": "x", "b": "0"})
    r = mc_run(m, seed=42, n=50_000)
    assert r["options"]["a"]["mean"] == pytest.approx(50.0, abs=0.5)


def test_event_mean_sanity():
    m = _map([_event("e", 0.3)], {"a": "e * 100", "b": "0"})
    r = mc_run(m, seed=42, n=50_000)
    assert r["options"]["a"]["mean"] == pytest.approx(30.0, abs=1.0)


def test_percentile_ordering():
    r = mc_run(_spec_map(), seed=42, n=5000)
    for stats in r["options"].values():
        assert stats["p10"] <= stats["median"] <= stats["p90"]


def test_triangular_within_bounds():
    m = _map([_cont("x", 20, 40, 90)], {"a": "x", "b": "0"})
    r = mc_run(m, seed=42, n=10_000)
    assert r["options"]["a"]["p10"] >= 20
    assert r["options"]["a"]["p90"] <= 90


# ── честное попарное сравнение (общий env на сценарий) ──────────────────────

def test_dominant_option_certain_win():
    m = _map([_cont("x", 0, 50, 100)], {"a": "x + 10", "b": "x"})
    r = mc_run(m, seed=42, n=5000)
    assert r["pairwise"]["a"]["b"] == 1.0
    assert r["pairwise"]["b"]["a"] == 0.0
    assert r["p_best"]["a"] == 1.0
    assert r["p_best"]["b"] == 0.0


def test_identical_options_are_ties():
    # один env на сценарий: x и x*1 совпадают в каждом сценарии → 0.5 везде
    m = _map([_cont("x", 0, 50, 100)], {"a": "x", "b": "x * 1"})
    r = mc_run(m, seed=42, n=1000)
    assert r["pairwise"]["a"]["b"] == 0.5
    assert r["p_best"]["a"] == 0.5
    assert r["p_best"]["b"] == 0.5


def test_pairwise_complementarity_and_pbest_sums_to_one():
    r = mc_run(_spec_map(), seed=42, n=3000)
    assert r["pairwise"]["ship_public"]["status_quo"] + \
        r["pairwise"]["status_quo"]["ship_public"] == pytest.approx(1.0)
    assert sum(r["p_best"].values()) == pytest.approx(1.0)


# ── regret ──────────────────────────────────────────────────────────────────

def test_regret_nonnegative():
    r = mc_run(_spec_map(), seed=42, n=3000)
    assert all(v >= 0 for v in r["expected_regret"].values())


def test_dominant_option_zero_regret():
    m = _map([_cont("x", 0, 50, 100)], {"a": "x + 10", "b": "x"})
    r = mc_run(m, seed=42, n=2000)
    assert r["expected_regret"]["a"] == 0.0
    assert r["expected_regret"]["b"] == pytest.approx(10.0)


# ── direction=min инвертирует честно ────────────────────────────────────────

def test_direction_min_inverts_winner():
    unc = [_cont("x", 0, 50, 100)]
    model = {"a": "x + 10", "b": "x"}
    r_max = mc_run(_map(unc, model, direction="max"), seed=42, n=2000)
    r_min = mc_run(_map(unc, model, direction="min"), seed=42, n=2000)
    assert r_max["p_best"]["a"] == 1.0
    assert r_min["p_best"]["b"] == 1.0
    assert r_min["pairwise"]["b"]["a"] == 1.0
    # regret тоже инвертируется: при min доминирует b
    assert r_min["expected_regret"]["b"] == 0.0
    assert r_min["expected_regret"]["a"] == pytest.approx(10.0)


# ── торнадо ─────────────────────────────────────────────────────────────────

def test_tornado_picks_dominant_uncertainty():
    # big двигает исход на порядки сильнее small
    m = _map([_cont("big", 0, 500, 1000), _cont("small", 0, 1, 2)],
             {"a": "big + small", "b": "0"})
    r = mc_run(m, seed=42, n=5000)
    assert r["top_uncertainties"][0] == "big"
    impacts = {t["id"]: t["impact"] for t in r["tornado"]}
    assert impacts["big"] > impacts["small"]


def test_tornado_sorted_and_complete():
    r = mc_run(_spec_map(), seed=42, n=3000)
    ids = [t["id"] for t in r["tornado"]]
    assert sorted(ids) == sorted(["traction_prob", "hours_to_ship", "upside_hours"])
    impacts = [t["impact"] for t in r["tornado"]]
    assert impacts == sorted(impacts, reverse=True)
    assert len(r["top_uncertainties"]) == 2
    assert r["top_uncertainties"] == ids[:2]


def test_tornado_unused_uncertainty_near_zero():
    # ghost не входит в формулу лидера → вклад ~0, доминирует big
    m = _map([_cont("big", 0, 500, 1000), _cont("ghost", 0, 50, 100)],
             {"a": "big", "b": "0"})
    r = mc_run(m, seed=42, n=5000)
    impacts = {t["id"]: t["impact"] for t in r["tornado"]}
    assert r["top_uncertainties"][0] == "big"
    assert impacts["ghost"] < 0.1
    assert impacts["big"] > 0.9


# ── лейбл «📐 рамка» ─────────────────────────────────────────────────────────

def test_label_contents():
    r = mc_run(_spec_map(), seed=123, n=777)
    assert r["label"] == {"n_uncertainties": 3, "seed": 123, "n": 777,
                          "confirmed": True}


def test_default_n():
    r = mc_run(_spec_map(), seed=1)
    assert r["label"]["n"] == 10_000


# ── fail-closed ─────────────────────────────────────────────────────────────

def test_invalid_map_refuses_to_run():
    m = _spec_map()
    m["uncertainties"][0]["confirmed_by_user"] = False
    with pytest.raises(ValueError) as e:
        mc_run(m, seed=42, n=100)
    assert "traction_prob" in str(e.value)


def test_division_by_zero_fails_whole_run():
    # e даёт 0.0 примерно в половине сценариев → формула a делит на ноль →
    # весь расчёт падает (fail-closed), а не «пропускаем сценарий»
    m = _map([_event("e", 0.5)], {"a": "1 / e", "b": "0"})
    with pytest.raises(ValueError):
        mc_run(m, seed=42, n=200)


def test_bad_n_and_seed_rejected():
    with pytest.raises(ValueError):
        mc_run(_spec_map(), seed=42, n=0)
    with pytest.raises(ValueError):
        mc_run(_spec_map(), seed=42, n=-5)
    with pytest.raises(ValueError):
        mc_run(_spec_map(), seed="сорок два", n=100)
