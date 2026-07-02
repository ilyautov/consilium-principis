"""Гейты честности карты решения — тесты validate_map (спека §2, fail-closed).

Каждый гейт покрыт позитивом (валидная карта → []) и негативом (нарушение →
человеческая RU-ошибка в списке). Расчёт без валидной карты не запускается —
тот же принцип, что no-manifest→A.

Отступления от плоского примера спеки (задокументированы в scripts/decision_map.py):
  • model — per-option объекты {"expr": ..., "words": ...} вместо плоской строки
    и общего "_описание": юзер визирует словесную версию КАЖДОЙ формулы.
  • статус-кво определяется явным флагом "status_quo": true (ровно на одном
    варианте), а не угадыванием по имени.
"""
import copy
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import decision_map
from decision_map import validate_map


def _valid_map():
    """Валидная карта из спеки §1 (в per-option форме модели)."""
    return {
        "question": "Куда вкладывать следующий месяц?",
        "options": [
            {"id": "ship_public", "name": "Выпустить публично",
             "description": "…", "reversibility": "one-way"},
            {"id": "status_quo", "name": "Ничего не делать",
             "description": "…", "reversibility": "two-way", "status_quo": True},
        ],
        "uncertainties": [
            {"id": "traction_prob", "kind": "event", "prob": 0.3,
             "confirmed_by_user": True, "elicited": "цитата ответа юзера"},
            {"id": "hours_to_ship", "kind": "continuous", "unit": "часы",
             "min": 20, "mode": 40, "max": 90,
             "confirmed_by_user": True, "elicited": "…"},
            {"id": "upside_hours", "kind": "continuous", "unit": "часы",
             "min": 50, "mode": 150, "max": 400,
             "confirmed_by_user": True, "elicited": "…"},
        ],
        "stakes": {"metric": "ценность в часах", "direction": "max"},
        "horizon": "3 месяца",
        "model": {
            "ship_public": {
                "expr": "traction_prob * upside_hours - hours_to_ship",
                "words": "вероятность трекшена умножить на выигрыш в часах, минус часы на шиппинг",
            },
            "status_quo": {"expr": "0", "words": "ничего не делаем — ноль часов"},
        },
    }


def _errors(mutate):
    m = _valid_map()
    mutate(m)
    return validate_map(m)


# ── позитив ─────────────────────────────────────────────────────────────────

def test_valid_map_passes():
    assert validate_map(_valid_map()) == []


def test_situational_optional():
    m = _valid_map()
    m["situational"] = {"you": "…", "opponent": "…", "stance": "comp"}
    assert validate_map(m) == []


def test_direction_min_valid():
    m = _valid_map()
    m["stakes"]["direction"] = "min"
    assert validate_map(m) == []


def test_degenerate_triangular_allowed():
    # min == mode == max — константа, допустимо (юзер уверен в числе)
    m = _valid_map()
    u = m["uncertainties"][1]
    u["min"] = u["mode"] = u["max"] = 40
    assert validate_map(m) == []


# ── структура ───────────────────────────────────────────────────────────────

def test_non_dict_map():
    assert validate_map(None) != []
    assert validate_map([]) != []
    assert validate_map("карта") != []


def test_errors_are_human_russian_strings():
    errs = validate_map({})
    assert errs and all(isinstance(e, str) and e for e in errs)
    joined = " ".join(errs).lower()
    assert any("а" <= ch <= "я" or ch == "ё" for ch in joined)
    # не стектрейс
    assert "traceback" not in joined


# ── гейт: confirmed_by_user на каждой величине ──────────────────────────────

def test_unconfirmed_uncertainty_blocks():
    errs = _errors(lambda m: m["uncertainties"][0].pop("confirmed_by_user"))
    assert any("traction_prob" in e for e in errs)


def test_confirmed_false_blocks():
    errs = _errors(lambda m: m["uncertainties"][1].update(confirmed_by_user=False))
    assert any("hours_to_ship" in e for e in errs)


def test_confirmed_string_true_blocks():
    # fail-closed: только литеральный True, никакой коэрсии строк
    errs = _errors(lambda m: m["uncertainties"][1].update(confirmed_by_user="true"))
    assert any("hours_to_ship" in e for e in errs)


# ── гейт: min <= mode <= max, prob в [0,1] ──────────────────────────────────

def test_min_above_mode_blocks():
    errs = _errors(lambda m: m["uncertainties"][1].update(min=50))
    assert any("hours_to_ship" in e for e in errs)


def test_mode_above_max_blocks():
    errs = _errors(lambda m: m["uncertainties"][2].update(mode=500))
    assert any("upside_hours" in e for e in errs)


@pytest.mark.parametrize("bad_prob", [-0.1, 1.5, "0.3", None, True])
def test_bad_prob_blocks(bad_prob):
    errs = _errors(lambda m: m["uncertainties"][0].update(prob=bad_prob))
    assert any("traction_prob" in e for e in errs)


def test_prob_bounds_inclusive():
    m = _valid_map()
    m["uncertainties"][0]["prob"] = 0.0
    assert validate_map(m) == []
    m["uncertainties"][0]["prob"] = 1.0
    assert validate_map(m) == []


def test_missing_min_blocks():
    errs = _errors(lambda m: m["uncertainties"][1].pop("min"))
    assert any("hours_to_ship" in e for e in errs)


@pytest.mark.parametrize("bad", ["20", None, True])
def test_non_numeric_bound_blocks(bad):
    errs = _errors(lambda m: m["uncertainties"][1].update(mode=bad))
    assert any("hours_to_ship" in e for e in errs)


# ── гейт: kind ∈ {continuous, event} ────────────────────────────────────────

@pytest.mark.parametrize("bad_kind", ["normal", "", None])
def test_bad_kind_blocks(bad_kind):
    errs = _errors(lambda m: m["uncertainties"][0].update(kind=bad_kind))
    assert any("traction_prob" in e for e in errs)


def test_missing_kind_blocks():
    errs = _errors(lambda m: m["uncertainties"][0].pop("kind"))
    assert any("traction_prob" in e for e in errs)


# ── гейт: uncertainties непусты, id уникальны ───────────────────────────────

def test_empty_uncertainties_blocks():
    errs = _errors(lambda m: m.update(uncertainties=[]))
    assert errs != []


def test_duplicate_uncertainty_id_blocks():
    def dup(m):
        m["uncertainties"].append(copy.deepcopy(m["uncertainties"][0]))
    errs = _errors(dup)
    assert any("traction_prob" in e for e in errs)


def test_uncertainty_without_id_blocks():
    errs = _errors(lambda m: m["uncertainties"][0].pop("id"))
    assert errs != []


# ── гейт: stakes + horizon ──────────────────────────────────────────────────

def test_missing_stakes_blocks():
    errs = _errors(lambda m: m.pop("stakes"))
    assert errs != []


def test_missing_horizon_blocks():
    errs = _errors(lambda m: m.pop("horizon"))
    assert errs != []


def test_empty_horizon_blocks():
    errs = _errors(lambda m: m.update(horizon="  "))
    assert errs != []


@pytest.mark.parametrize("bad_dir", ["up", "", None])
def test_bad_direction_blocks(bad_dir):
    errs = _errors(lambda m: m["stakes"].update(direction=bad_dir))
    assert errs != []


def test_missing_metric_blocks():
    errs = _errors(lambda m: m["stakes"].pop("metric"))
    assert errs != []


# ── гейт: >= 2 options, статус-кво присутствует ─────────────────────────────

def test_single_option_blocks():
    def cut(m):
        m["options"] = m["options"][1:]
        m["model"].pop("ship_public")
    errs = _errors(cut)
    assert errs != []


def test_no_status_quo_flag_blocks():
    errs = _errors(lambda m: m["options"][1].pop("status_quo"))
    assert any("статус-кво" in e.lower() for e in errs)


def test_two_status_quo_blocks():
    errs = _errors(lambda m: m["options"][0].update(status_quo=True))
    assert any("статус-кво" in e.lower() for e in errs)


def test_status_quo_string_true_blocks():
    # fail-closed: флаг — литеральный True
    def mut(m):
        m["options"][1]["status_quo"] = "true"
    errs = _errors(mut)
    assert any("статус-кво" in e.lower() for e in errs)


def test_duplicate_option_id_blocks():
    errs = _errors(lambda m: m["options"][0].update(id="status_quo"))
    assert any("status_quo" in e for e in errs)


def test_option_without_id_blocks():
    errs = _errors(lambda m: m["options"][0].pop("id"))
    assert errs != []


# ── гейт: формула на каждый вариант, парсится, только известные id ──────────

def test_option_missing_in_model_blocks():
    errs = _errors(lambda m: m["model"].pop("ship_public"))
    assert any("ship_public" in e for e in errs)


def test_model_extra_key_blocks():
    # ключ модели без соответствующего варианта — рассинхрон карты, отказ
    errs = _errors(lambda m: m["model"].update(
        ghost_option={"expr": "0", "words": "призрак"}))
    assert any("ghost_option" in e for e in errs)


def test_missing_model_blocks():
    errs = _errors(lambda m: m.pop("model"))
    assert errs != []


def test_unknown_id_in_formula_blocks():
    def mut(m):
        m["model"]["ship_public"]["expr"] = "traction_prob * unknown_var"
    errs = _errors(mut)
    assert any("unknown_var" in e for e in errs)


def test_option_id_not_usable_in_formula():
    # id вариантов — НЕ величины; в env их нет → отказ на компиляции
    def mut(m):
        m["model"]["ship_public"]["expr"] = "status_quo + 1"
    errs = _errors(mut)
    assert errs != []


def test_unparseable_formula_blocks():
    def mut(m):
        m["model"]["ship_public"]["expr"] = "__import__('os')"
    errs = _errors(mut)
    assert any("ship_public" in e for e in errs)


def test_formula_syntax_error_blocks():
    def mut(m):
        m["model"]["ship_public"]["expr"] = "traction_prob *"
    errs = _errors(mut)
    assert errs != []


# ── гейт: словесная версия формулы ──────────────────────────────────────────

def test_missing_words_blocks():
    errs = _errors(lambda m: m["model"]["ship_public"].pop("words"))
    assert any("ship_public" in e for e in errs)


def test_empty_words_blocks():
    errs = _errors(lambda m: m["model"]["ship_public"].update(words="  "))
    assert any("ship_public" in e for e in errs)


def test_flat_string_model_blocks():
    # плоская форма из примера спеки не принимается — только {"expr", "words"}
    def mut(m):
        m["model"]["ship_public"] = "traction_prob * upside_hours - hours_to_ship"
    errs = _errors(mut)
    assert any("ship_public" in e for e in errs)


# ── аккумуляция: все ошибки разом, не первая ────────────────────────────────

def test_multiple_errors_accumulate():
    def mut(m):
        m["uncertainties"][0].pop("confirmed_by_user")
        m.pop("horizon")
        m["model"]["status_quo"].pop("words")
    errs = _errors(mut)
    assert len(errs) >= 3


# ── константы схемы экспортированы ──────────────────────────────────────────

def test_schema_constants():
    assert decision_map.KIND_CONTINUOUS == "continuous"
    assert decision_map.KIND_EVENT == "event"
    assert decision_map.KINDS == {"continuous", "event"}
    assert decision_map.DIRECTIONS == {"max", "min"}
