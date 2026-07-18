"""Decision Card — схема + fail-closed гейты (decision-lifecycle §2.1-2.3).

Card — единственный персистентный узел жизненного цикла: UUID (dc_…), версия схемы,
владелец, дата ревью, ссылки на карту/сессию/ситуацию, выбранный вариант, допущения,
критерий успеха, prediction contract и (при закрытии) outcome. Все гейты — тот же
принцип, что validate_map: аккумулируют ВСЕ ошибки RU-строками, не первую (host задаёт
их юзеру как вопросы совета). Ноль LLM, ноль сети.
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import decision_card as dc  # noqa: E402


def _min_card(**over):
    """Минимальная валидная Card (event-прогноз, без ссылки на карту)."""
    card = {
        "schema_version": dc.SCHEMA_VERSION,
        "id": dc.new_card_id(),
        "created": "2026-07-18",
        "owner": "self",
        "kind": "decision_card",
        "links": {"map_path": None, "session_id": None, "situation_ref": None},
        "question": "Шипнуть публично или ждать?",
        "chosen_option": "ship_public",
        "assumptions": [{"text": "спрос ≥ 100/мес", "uncertainty_id": "demand"}],
        "success_criterion": {"text": "≥ 100 платящих за 90 дней",
                              "prediction_ref": "pred_ship"},
        "reversibility": "one-way",
        "review_date": "2026-10-16",
        "review_horizon_days": 90,
        "prediction": {
            "id": "pred_ship",
            "kind": "event",
            "statement": "≥ 100 платящих за 90 дней",
            "probability": 0.72,
            "horizon_days": 90,
            "resolves_on": "2026-10-16",
        },
        "outcome": None,
    }
    card.update(over)
    return card


def _metric_prediction(**over):
    p = {
        "id": "pred_demand",
        "kind": "metric",
        "statement": "число платящих на 90-й день",
        "unit": "платящих",
        "p10": 60, "p50": 105, "p90": 180,
        "direction": "max",
        "horizon_days": 90,
        "resolves_on": "2026-10-16",
    }
    p.update(over)
    return p


# ── new_card_id / SCHEMA_VERSION ────────────────────────────────────────────

def test_new_card_id_matches_dc_pattern():
    cid = dc.new_card_id()
    assert re.fullmatch(r"dc_[A-Za-z0-9]+", cid), cid


def test_new_card_id_is_unique():
    assert dc.new_card_id() != dc.new_card_id()


def test_schema_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", dc.SCHEMA_VERSION)


# ── validate_card: happy path ───────────────────────────────────────────────

def test_valid_event_card_passes():
    assert dc.validate_card(_min_card()) == []


def test_valid_metric_card_passes():
    card = _min_card(prediction=_metric_prediction(),
                     success_criterion={"text": "…", "prediction_ref": "pred_demand"})
    assert dc.validate_card(card) == []


def test_defer_card_null_chosen_option_passes():
    assert dc.validate_card(_min_card(chosen_option=None)) == []


# ── validate_card: structural gates (fail-closed, RU-строки, аккумулируются) ─

def test_missing_id_flagged():
    card = _min_card()
    del card["id"]
    errs = dc.validate_card(card)
    assert errs and any("id" in e.lower() for e in errs)


def test_bad_id_pattern_flagged():
    errs = dc.validate_card(_min_card(id="whatever-123"))
    assert any("dc_" in e for e in errs)


def test_missing_schema_version_flagged():
    card = _min_card()
    del card["schema_version"]
    assert any("схем" in e.lower() or "версия" in e.lower() for e in dc.validate_card(card))


def test_wrong_kind_flagged():
    assert any("decision_card" in e for e in dc.validate_card(_min_card(kind="decision_map")))


def test_empty_owner_flagged():
    assert any("владел" in e.lower() for e in dc.validate_card(_min_card(owner="  ")))


def test_review_date_before_created_flagged():
    errs = dc.validate_card(_min_card(created="2026-07-18", review_date="2026-07-01"))
    assert any("ревью" in e.lower() for e in errs)


def test_bad_review_date_flagged():
    assert any("ревью" in e.lower() or "дат" in e.lower()
               for e in dc.validate_card(_min_card(review_date="не-дата")))


def test_reversibility_bad_value_flagged():
    assert any("revers" in e.lower() or "обратим" in e.lower()
               for e in dc.validate_card(_min_card(reversibility="maybe")))


def test_reversibility_optional_absent_ok():
    card = _min_card()
    del card["reversibility"]
    assert dc.validate_card(card) == []


def test_errors_accumulate_not_first():
    # сразу три дефекта: id, owner, review_date — все должны прийти разом
    card = _min_card(id="bad", owner="", review_date="2000-01-01")
    errs = dc.validate_card(card)
    assert len(errs) >= 3


# ── validate_card against map: chosen_option membership ──────────────────────

def _map():
    return {
        "options": [{"id": "ship_public", "status_quo": False},
                    {"id": "status_quo", "status_quo": True}],
        "stakes": {"metric": "платящих", "direction": "max"},
    }


def test_chosen_option_must_be_in_map_options():
    errs = dc.validate_card(_min_card(chosen_option="not_an_option"), map=_map())
    assert any("вариант" in e.lower() for e in errs)


def test_chosen_option_in_map_passes():
    assert dc.validate_card(_min_card(chosen_option="ship_public"), map=_map()) == []


def test_empty_string_chosen_option_rejected():
    # пустая строка ≠ явный defer (None) — fail-closed
    assert dc.validate_card(_min_card(chosen_option=""), map=_map())


# ── prediction contract gates ───────────────────────────────────────────────

def test_event_probability_out_of_range_flagged():
    assert any("вероятн" in e.lower() for e in
               dc.validate_card(_min_card(prediction={
                   "id": "p", "kind": "event", "statement": "x",
                   "probability": 1.5, "horizon_days": 90})))


def test_metric_percentile_order_violated_flagged():
    bad = _metric_prediction(p10=200, p50=105, p90=180)
    errs = dc.validate_card(_min_card(prediction=bad,
                            success_criterion={"text": "x", "prediction_ref": "pred_demand"}))
    assert any("p10" in e or "перцентил" in e.lower() for e in errs)


def test_metric_missing_unit_flagged():
    bad = _metric_prediction()
    del bad["unit"]
    errs = dc.validate_card(_min_card(prediction=bad,
                            success_criterion={"text": "x", "prediction_ref": "pred_demand"}))
    assert any("единиц" in e.lower() for e in errs)


def test_metric_bad_direction_flagged():
    bad = _metric_prediction(direction="sideways")
    errs = dc.validate_card(_min_card(prediction=bad,
                            success_criterion={"text": "x", "prediction_ref": "pred_demand"}))
    assert any("направлен" in e.lower() for e in errs)


def test_prediction_bad_kind_flagged():
    assert any("вид" in e.lower() or "kind" in e.lower() for e in
               dc.validate_card(_min_card(prediction={
                   "id": "p", "kind": "guess", "statement": "x", "horizon_days": 1})))


def test_horizon_days_must_be_positive_int():
    assert any("горизонт" in e.lower() or "срок" in e.lower() for e in
               dc.validate_card(_min_card(prediction={
                   "id": "p", "kind": "event", "statement": "x",
                   "probability": 0.5, "horizon_days": 0})))


def test_event_probability_nan_rejected():
    assert any("вероятн" in e.lower() for e in
               dc.validate_card(_min_card(prediction={
                   "id": "p", "kind": "event", "statement": "x",
                   "probability": float("inf"), "horizon_days": 5})))


# ── outcome gates (при закрытии) ────────────────────────────────────────────

def test_event_outcome_needs_occurred_bool():
    card = _min_card(outcome={"resolved_on": "2026-10-14", "occurred": "yes"})
    assert any("occurred" in e or "событ" in e.lower() for e in dc.validate_card(card))


def test_metric_outcome_actual_must_be_number():
    card = _min_card(prediction=_metric_prediction(),
                     success_criterion={"text": "x", "prediction_ref": "pred_demand"},
                     outcome={"resolved_on": "2026-10-14", "actual": "много"})
    assert any("actual" in e or "числ" in e.lower() for e in dc.validate_card(card))


def test_valid_event_outcome_passes():
    card = _min_card(outcome={"resolved_on": "2026-10-14", "occurred": True,
                              "endorsed": True, "note": "легло"})
    assert dc.validate_card(card) == []


def test_valid_metric_outcome_passes():
    card = _min_card(prediction=_metric_prediction(),
                     success_criterion={"text": "x", "prediction_ref": "pred_demand"},
                     outcome={"resolved_on": "2026-10-14", "actual": 130, "endorsed": False})
    assert dc.validate_card(card) == []


def test_outcome_resolved_before_created_flagged():
    card = _min_card(created="2026-07-18",
                     outcome={"resolved_on": "2026-07-01", "occurred": True})
    assert any("resolved" in e.lower() or "закрыт" in e.lower() or "раньше" in e.lower()
               for e in dc.validate_card(card))


# ── close_card: fail-closed переход open → closed ───────────────────────────

def test_close_card_sets_outcome_and_validates():
    card = _min_card()
    closed = dc.close_card(card, {"resolved_on": "2026-10-14", "occurred": True,
                                  "endorsed": True})
    assert closed["outcome"]["occurred"] is True
    assert card["outcome"] is None            # исходная карта не мутируется


def test_close_card_rejects_bad_outcome():
    with pytest.raises(ValueError):
        dc.close_card(_min_card(), {"resolved_on": "2026-10-14", "occurred": "maybe"})


def test_close_card_metric_wrong_type_rejected():
    card = _min_card(prediction=_metric_prediction(),
                     success_criterion={"text": "x", "prediction_ref": "pred_demand"})
    with pytest.raises(ValueError):
        dc.close_card(card, {"resolved_on": "2026-10-14", "actual": "нет"})


# ── не-dict вход ────────────────────────────────────────────────────────────

def test_non_dict_card_returns_error():
    assert dc.validate_card(["не", "карта"])
    assert dc.validate_card(None)
