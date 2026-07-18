"""Quality-gate на retrieval/abstention (спека 2026-07-18 узел 2, Вариант C — слои 1+2).

Слой 1: eval.py --emit-metrics → стратифицированный машинный артефакт (форма moat-baseline)
        со стратами ru/en/ooc, backend и per-advisor corpus_sha256. Фикс load_golden,
        терявшего .en-golden (eval.py:242 грузил только {name}.{kind}).

Слой 2: ОФФЛАЙН pytest-гейт на ЗАМОРОЖЕННЫХ скорах — проверяет МАТЕМАТИКУ метрик и парсинг
        (retrieval_regression.metrics_from_frozen / run_gate), БЕЗ сети и без живого retrieve.
        Ловит регресс кода метрик/порогов; регресс движка ловит слой-3 refresh (ритуал владельца).

Слой 3 (human-review semantic-refresh на машине владельца) — НЕ здесь: см.
        docs/dev/retrieval-regression-refresh.md.
"""
import os
import sys
import json

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import retrieval_regression as rr  # noqa: E402
import eval as ev  # noqa: E402


# ───────────────────────── слой 2: математика метрик из замороженных скоров ─────────────────

def test_metrics_from_frozen_matches_hand_math():
    frozen = {
        "ooc_scores": [0.0, 0.1, 0.2, 0.3],      # должны отказать (ниже порога)
        "ans_scores": [0.6, 0.7, 0.8, 0.9],      # должны ответить (выше порога)
        "retrieval": {
            "ru": {"hit1": [True, True, False, False], "hit3": [True, True, True, False]},
            "en": {"hit1": [True, True, True, True], "hit3": [True, True, True, True]},
        },
    }
    m = rr.metrics_from_frozen(frozen, threshold=0.5)
    # порог 0.5: все 4 OOC ниже → honest 1.0; все 4 answerable выше → false_abstain 0.0
    assert m["ooc"]["honest_abstain"] == 1.0
    assert m["ooc"]["false_abstain"] == 0.0
    assert m["ooc"]["auc"] == 1.0                # OOC полностью ниже answerable
    assert m["ru"]["top1"] == 0.5 and m["ru"]["top3"] == 0.75
    assert m["en"]["top1"] == 1.0


def _baseline_from(frozen, threshold=0.5, sha="abc123", backend="lexical"):
    m = rr.metrics_from_frozen(frozen, threshold=threshold)
    strata = {}
    for k, v in m.items():
        strata[k] = dict(v)
        if k == "ooc":
            strata[k]["threshold"] = threshold
    return {"meta": {"backend": backend, "corpus_sha256": {"sage": sha}},
            "advisors": {"sage": {"corpus_sha256": sha, "strata": strata}}}


def _fixture_from(frozen, sha="abc123"):
    return {"meta": {"corpus_sha256": {"sage": sha}},
            "advisors": {"sage": dict(frozen, corpus_sha256=sha)}}


_GOOD = {
    "ooc_scores": [0.0, 0.1, 0.2, 0.3], "ans_scores": [0.6, 0.7, 0.8, 0.9],
    "retrieval": {"ru": {"hit1": [True, True, False, False], "hit3": [True, True, True, False]}},
}


def test_gate_passes_when_fixture_equals_baseline():
    res = rr.run_gate(_fixture_from(_GOOD), _baseline_from(_GOOD))
    assert res["ok"] is True and not res["failures"]


def test_gate_fails_on_recall_regression_beyond_tolerance():
    worse = json.loads(json.dumps(_GOOD))
    worse["retrieval"]["ru"]["hit1"] = [False, False, False, False]  # top1 1.0→0.0
    res = rr.run_gate(_fixture_from(worse), _baseline_from(_GOOD), tolerance={"top1": 0.1})
    assert res["ok"] is False
    assert any("top1" in f for f in res["failures"])


def test_gate_fails_on_stale_corpus_sha():
    res = rr.run_gate(_fixture_from(_GOOD, sha="NEWHASH"), _baseline_from(_GOOD, sha="OLDHASH"))
    assert res["ok"] is False
    assert any("corpus_sha256" in f or "stale" in f.lower() or "устар" in f.lower()
               for f in res["failures"])


def test_gate_skips_degenerate_stratum():
    # degenerate-страта (кросс-язык на lexical) — числа недостоверны, сравнивать нельзя → пропуск.
    deg = json.loads(json.dumps(_GOOD))
    deg["retrieval"]["ru"]["hit1"] = [False, False, False, False]
    deg["retrieval"]["ru"]["degenerate"] = True
    res = rr.run_gate(_fixture_from(deg), _baseline_from(_GOOD), tolerance={"top1": 0.1})
    assert res["ok"] is True, "degenerate-страта должна пропускаться, не валить гейт"


def test_gate_fails_on_false_abstain_growth():
    # false_abstain: ниже — лучше; рост сверх tolerance = регресс (over-abstention).
    worse = json.loads(json.dumps(_GOOD))
    worse["ans_scores"] = [0.0, 0.0, 0.0, 0.0]   # все answerable теперь ниже порога → false_ab 1.0
    res = rr.run_gate(_fixture_from(worse), _baseline_from(_GOOD), tolerance={"false_abstain": 0.1})
    assert res["ok"] is False
    assert any("false_abstain" in f for f in res["failures"])


# ───────────────────────── слой 1: load_golden .en + emit-metrics стратификация ─────────────

def _mk_advisor(tmp_path):
    adv = tmp_path / "advisors" / "sage"
    (adv / "build").mkdir(parents=True)
    rows = [
        {"source": "s.txt", "tier": "P1",
         "text": "Power rests on appearances. Fortune favors the bold prince. "
                 "Winning without fighting is the acme of skill."},
    ]
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(adv)


def _write_golden(golden_dir, name, kind, rows, lang=None):
    suffix = f".{lang}" if lang else ""
    with open(os.path.join(golden_dir, f"{name}.{kind}{suffix}.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_load_golden_picks_up_en_variant(tmp_path, monkeypatch):
    """Регресс-гард против eval.py:242 — раньше .en молча терялся, EN-стратум не считался."""
    gd = tmp_path / "golden"; gd.mkdir()
    monkeypatch.setattr(ev, "GOLDEN_DIR", str(gd))
    _write_golden(str(gd), "sage", "retrieval", [{"q": "как удержать власть", "anchor": "appearances", "ref": "ru1"}])
    _write_golden(str(gd), "sage", "retrieval", [{"q": "how to hold power", "anchor": "appearances", "ref": "en1"}], lang="en")
    ru, _ = ev.load_golden("sage", "retrieval")
    en, _ = ev.load_golden("sage", "retrieval", lang="en")
    assert ru and en
    assert ru[0]["ref"] == "ru1" and en[0]["ref"] == "en1"


def test_emit_metrics_stratifies_ru_en_ooc(tmp_path, monkeypatch):
    gd = tmp_path / "golden"; gd.mkdir()
    monkeypatch.setattr(ev, "GOLDEN_DIR", str(gd))
    adv = _mk_advisor(tmp_path)
    _write_golden(str(gd), "sage", "retrieval",
                  [{"q": "appearances of power", "anchor": "appearances", "ref": "ru1"}])
    _write_golden(str(gd), "sage", "retrieval",
                  [{"q": "acme of skill winning", "anchor": "acme of skill", "ref": "en1"}], lang="en")
    _write_golden(str(gd), "sage", "abstention",
                  [{"q": "unrelated question about blockchain and crypto taxes"}])
    metrics = ev.build_metrics([adv], "lexical")
    assert metrics["meta"]["backend"] == "lexical"
    assert "sage" in metrics["meta"]["corpus_sha256"]
    strata = metrics["advisors"]["sage"]["strata"]
    assert set(strata) >= {"ru", "en", "ooc"}
    # числа страты ru совпадают с retrieval_eval (тот же расчёт, только сериализованный)
    ru_eval = ev.retrieval_eval(adv)
    assert strata["ru"]["top1"] == ru_eval["top1"] and strata["ru"]["n"] == ru_eval["n"]


def test_emit_metrics_writes_file_via_main(tmp_path, monkeypatch):
    gd = tmp_path / "golden"; gd.mkdir()
    monkeypatch.setattr(ev, "GOLDEN_DIR", str(gd))
    adv = _mk_advisor(tmp_path)
    _write_golden(str(gd), "sage", "retrieval", [{"q": "appearances", "anchor": "appearances", "ref": "ru1"}])
    _write_golden(str(gd), "sage", "abstention", [{"q": "blockchain crypto taxes unrelated"}])
    out = tmp_path / "retrieval-metrics.json"
    # без --engine: main не трогает os.environ (герметичность); offline resolve → lexical
    ev.main([adv, "--emit-metrics", str(out)])
    assert out.is_file()
    data = json.load(open(out, encoding="utf-8"))
    assert "advisors" in data and "sage" in data["advisors"]
