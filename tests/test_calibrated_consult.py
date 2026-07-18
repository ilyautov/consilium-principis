"""Calibrated Consult — анти-оверрелайанс инструмент (спека 2026-07-18-calibrated-consult-design).

Инструмент делает оверрелайанс ВИДИМЫМ (prior→совет→posterior→зеркало→калибровка), НЕ заявляет
«снижает». Гейты — зеркало decision_card.validate_card: аккумулируют ВСЕ RU-ошибки, fail-closed,
ноль LLM/сети. Тесты синтетические, офлайн, приватных слагов нет.
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import calibrated_consult as cc  # noqa: E402


def _prior(**over):
    p = {"call": "ждать релиза", "confidence": 0.6, "abstain": False}
    p.update(over)
    return p


def _min_consult(**over):
    c = {
        "schema_version": cc.SCHEMA_VERSION,
        "id": cc.new_consult_id(),
        "created": "2026-07-18",
        "kind": cc.KIND_CONSULT,
        "question": "Шипнуть публично сейчас или ждать?",
        "prior": _prior(),
        "posterior": None,
        "mirror": None,
        "prediction": None,
        "outcome": None,
        "decision_card_ref": None,
    }
    c.update(over)
    return c


def test_new_consult_id_is_ulid_shape():
    body = cc.new_consult_id()[len(cc._ID_PREFIX):]
    assert len(body) == 26, body
    assert all(ch in cc._CROCKFORD for ch in body), body


def test_new_consult_id_matches_pattern():
    assert re.fullmatch(r"cc_[A-Za-z0-9]+", cc.new_consult_id())


def test_schema_version_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", cc.SCHEMA_VERSION)


def test_valid_open_consult_passes():
    assert cc.validate_consult(_min_consult()) == []


def test_missing_question_flagged():
    assert any("вопрос" in e.lower() for e in cc.validate_consult(_min_consult(question="  ")))


def test_bad_id_pattern_flagged():
    assert any("cc_" in e for e in cc.validate_consult(_min_consult(id="whatever-1")))


def test_prior_confidence_out_of_range_flagged():
    assert any("увер" in e.lower() for e in cc.validate_consult(_min_consult(prior=_prior(confidence=1.5))))


def test_prior_confidence_nan_flagged():
    assert any("увер" in e.lower() for e in cc.validate_consult(_min_consult(prior=_prior(confidence=float("nan")))))


def test_prior_empty_call_flagged():
    assert any("позици" in e.lower() or "call" in e.lower()
               for e in cc.validate_consult(_min_consult(prior=_prior(call=""))))


def test_prior_abstain_must_be_bool():
    assert any("воздерж" in e.lower() or "abstain" in e.lower()
               for e in cc.validate_consult(_min_consult(prior=_prior(abstain="yes"))))


def test_errors_accumulate_not_first():
    bad = _min_consult(id="bad", question="", prior=_prior(confidence=2.0, call=""))
    assert len(cc.validate_consult(bad)) >= 3


def test_non_dict_consult_returns_error():
    assert cc.validate_consult(["nope"])
    assert cc.validate_consult(None)


def test_build_consult_shape_and_valid():
    c = cc.build_consult("Шипнуть сейчас?", "ждать", 0.6, prior_abstain=False,
                         created="2026-07-18")
    assert c["kind"] == cc.KIND_CONSULT
    assert c["id"].startswith("cc_")
    assert c["prior"] == {"call": "ждать", "confidence": 0.6, "abstain": False}
    assert c["posterior"] is None and c["mirror"] is None and c["outcome"] is None
    assert cc.validate_consult(c) == []


def test_build_consult_respects_given_id_and_created():
    c = cc.build_consult("q", "call", 0.5, created="2026-01-02", consult_id="cc_FIXED1")
    assert c["id"] == "cc_FIXED1" and c["created"] == "2026-01-02"


def test_mirror_confidence_delta_and_shift():
    m = cc.compute_mirror({"call": "ждать", "confidence": 0.6, "abstain": False},
                          {"call": "шипнуть", "confidence": 0.85, "abstain": False})
    assert abs(m["confidence_delta"] - 0.25) < 1e-9
    assert m["shifted"] is True
    assert m["abstention_dropped"] is False


def test_mirror_no_shift_normalized():
    # разный регистр/пробелы — та же позиция → не сдвиг
    m = cc.compute_mirror({"call": "Ждать релиза", "confidence": 0.6, "abstain": False},
                          {"call": "  ждать  релиза ", "confidence": 0.6, "abstain": False})
    assert m["shifted"] is False
    assert m["confidence_delta"] == 0.0


def test_mirror_abstention_dropped_is_core_signal():
    # был «не знаю» (abstain), после совета — уверенная позиция → ядро находки arXiv
    m = cc.compute_mirror({"call": "не знаю", "confidence": 0.2, "abstain": True},
                          {"call": "шипнуть", "confidence": 0.8, "abstain": False})
    assert m["abstention_dropped"] is True


def _metric_prediction(**over):
    p = {"id": "pred_x", "kind": "metric", "statement": "платящих на 90-й день",
         "unit": "платящих", "p10": 60, "p50": 105, "p90": 180,
         "direction": "max", "horizon_days": 90}
    p.update(over)
    return p


def test_close_sets_posterior_and_mirror_immutably():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.85, posterior_abstain=False,
                              followed_council=True)
    assert closed["posterior"]["call"] == "шипнуть"
    assert closed["posterior"]["followed_council"] is True
    assert abs(closed["mirror"]["confidence_delta"] - 0.25) < 1e-9
    assert c["posterior"] is None            # исходная запись не мутируется
    assert cc.validate_consult(closed) == []


def test_close_attaches_valid_prediction():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False,
                              followed_council=False, prediction=_metric_prediction())
    assert closed["prediction"]["kind"] == "metric"
    assert cc.validate_consult(closed) == []


def test_close_rejects_bad_posterior_confidence():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    with pytest.raises(ValueError):
        cc.close_consult(c, "шипнуть", 1.4, posterior_abstain=False, followed_council=True)


def test_close_rejects_bad_prediction():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    with pytest.raises(ValueError):
        cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False, followed_council=True,
                         prediction={"kind": "metric", "p10": 200, "p50": 105, "p90": 180,
                                     "unit": "x", "direction": "max", "statement": "s",
                                     "horizon_days": 90})


def test_close_rejects_already_closed():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False, followed_council=True)
    with pytest.raises(ValueError):
        cc.close_consult(closed, "снова", 0.7, posterior_abstain=False, followed_council=True)


def _closed_metric_consult():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    return cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False,
                            followed_council=True, prediction=_metric_prediction())


def test_resolve_sets_outcome_immutably():
    closed = _closed_metric_consult()
    resolved = cc.resolve_consult(closed, {"resolved_on": "2026-10-16", "actual": 130})
    assert resolved["outcome"]["actual"] == 130
    assert closed["outcome"] is None                 # копия, не мутация
    assert cc.validate_consult(resolved) == []


def test_resolve_rejects_wrong_type_outcome():
    closed = _closed_metric_consult()
    with pytest.raises(ValueError):
        cc.resolve_consult(closed, {"resolved_on": "2026-10-16", "actual": "много"})


def test_resolve_requires_prediction():
    # без прогноза резолвить нечего (калибровке не с чем сравнивать) → fail-closed
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False, followed_council=True)
    with pytest.raises(ValueError):
        cc.resolve_consult(closed, {"resolved_on": "2026-10-16", "occurred": True})


def _event_consult(prior_ab, post_ab, prior_c, post_c, followed, prob, occurred, cid):
    c = cc.build_consult("q", "call-a", prior_c, prior_abstain=prior_ab,
                         created="2026-07-18", consult_id=cid)
    closed = cc.close_consult(c, "call-b", post_c, posterior_abstain=post_ab,
                              followed_council=followed,
                              prediction={"id": "p", "kind": "event", "statement": "s",
                                          "probability": prob, "horizon_days": 30})
    return cc.resolve_consult(closed, {"resolved_on": "2026-08-17", "occurred": occurred})


def test_overreliance_journal_counts_mirror_signals():
    consults = [
        # инфляция уверенности +0.3, воздержание подавлено, следовал совету, но неверно (prob .9, occurred False)
        _event_consult(True, False, 0.5, 0.8, True, 0.9, False, "cc_AAAA1"),
        # без инфляции, не следовал, верно
        _event_consult(False, False, 0.6, 0.6, False, 0.7, True, "cc_BBBB2"),
    ]
    j = cc.overreliance_journal(consults, min_n=1)
    assert j["n_closed"] == 2
    assert abs(j["confidence_inflation"] - 0.15) < 1e-9      # mean(0.3, 0.0)
    assert j["abstention_suppressed"] == 1
    # bad-follow: калибровка followed=true хуже, чем followed=false (реюз Brier)
    assert j["followed"]["brier"] is not None and j["independent"]["brier"] is not None
    assert j["followed"]["brier"] > j["independent"]["brier"]


def test_overreliance_journal_trustworthy_threshold():
    j = cc.overreliance_journal([], min_n=5)
    assert j["n_closed"] == 0 and j["trustworthy"] is False


def test_overreliance_journal_ignores_open_consults():
    open_only = cc.build_consult("q", "call", 0.6, created="2026-07-18")
    j = cc.overreliance_journal([open_only], min_n=1)
    assert j["n_closed"] == 0


# ── edge cases: fail-closed на кривых записях (регресс-локи) ──────────────────

def test_close_rejects_missing_or_nondict_prior():
    # запись «с диска» без валидного prior → документированный ValueError, НЕ KeyError/AttributeError
    for bad_prior in (None, "не-объект", 42, ["list"]):
        rec = _min_consult(prior=bad_prior)
        with pytest.raises(ValueError):
            cc.close_consult(rec, "шипнуть", 0.8, posterior_abstain=False, followed_council=True)


def test_validate_consult_prior_non_dict_flagged_not_crash():
    # prior = строка → аккумулированная RU-ошибка, без исключения
    errs = cc.validate_consult(_min_consult(prior="ждать релиза"))
    assert any("приор" in e.lower() for e in errs)


def test_validate_consult_posterior_missing_followed_council_flagged():
    post = {"call": "шипнуть", "confidence": 0.8, "abstain": False}  # нет followed_council
    assert any("followed_council" in e for e in cc.validate_consult(_min_consult(posterior=post)))


def test_validate_consult_posterior_nonbool_followed_council_flagged():
    post = {"call": "шипнуть", "confidence": 0.8, "abstain": False, "followed_council": "yes"}
    assert any("followed_council" in e for e in cc.validate_consult(_min_consult(posterior=post)))


def test_prior_confidence_bounds_inclusive():
    # ровно 0.0 и ровно 1.0 валидны (замок на включающие границы <=)
    assert cc.validate_consult(_min_consult(prior=_prior(confidence=0.0))) == []
    assert cc.validate_consult(_min_consult(prior=_prior(confidence=1.0))) == []
