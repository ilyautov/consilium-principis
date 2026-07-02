"""§3.3 moat-v2: ритуал moat-check (moat_check).

Оффлайн: логика сравнения с базлайном / допуски / хэши / сборка прогона на сеамах —
без сети, без ollama. Живой прогон и создание базлайна — moat_check.main().
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import pytest
import moat_check


def _baseline(mis=0.20, cov=0.90, inflated=0, extra_adv=None):
    adv = {"machiavelli": {"misapply_rate": mis, "n_camouflage": 12,
                           "coverage": cov, "n_ans": 12,
                           "judge_ooc_false_accept": 0.1}}
    if extra_adv:
        adv[extra_adv] = dict(adv["machiavelli"])
    return {"meta": {"judge_model": "google/gemini-2.5-flash",
                     "hashes": {"judge_prompt": "aaa", "rubric": "bbb"},
                     "corpus_sha256": {"machiavelli": "c1"}},
            "advisors": adv,
            "injection": {"n": 14, "inflated_n": inflated, "inflation_rate": 0.0,
                          "gate_flips": 0, "mean_delta": 0.0, "max_delta": 0}}


def _run(mis=0.20, cov=0.90, inflated=0, flips=0, model="google/gemini-2.5-flash",
         hashes=None, corpus="c1"):
    r = _baseline(mis, cov, inflated)
    r["meta"]["judge_model"] = model
    r["meta"]["hashes"] = hashes or {"judge_prompt": "aaa", "rubric": "bbb"}
    r["meta"]["corpus_sha256"] = {"machiavelli": corpus}
    r["injection"]["gate_flips"] = flips
    return r


# ───────────────────────── compare: зелёные пути ─────────────────────────────

def test_identical_run_is_green():
    v = moat_check.compare(_baseline(), _run())
    assert v["ok"] and not v["failures"] and not v["warnings"]


def test_improvement_is_green():
    v = moat_check.compare(_baseline(), _run(mis=0.10, cov=0.95))
    assert v["ok"]


def test_degradation_within_tolerance_green():
    """+5 п.п. misapply и −5 п.п. coverage — ровно на границе допуска → зелёный."""
    v = moat_check.compare(_baseline(0.20, 0.90), _run(mis=0.25, cov=0.85))
    assert v["ok"], v["failures"]


# ───────────────────────── compare: деградации ───────────────────────────────

def test_misapply_beyond_tolerance_fails():
    v = moat_check.compare(_baseline(0.20), _run(mis=0.26))
    assert not v["ok"] and any("misapply" in f for f in v["failures"])


def test_coverage_beyond_tolerance_fails():
    v = moat_check.compare(_baseline(cov=0.90), _run(cov=0.84))
    assert not v["ok"] and any("coverage" in f for f in v["failures"])


def test_gate_flip_always_fails():
    v = moat_check.compare(_baseline(), _run(flips=1))
    assert not v["ok"] and any("gate_flips" in f for f in v["failures"])


def test_inflation_growth_fails_but_equal_is_green():
    assert not moat_check.compare(_baseline(inflated=0), _run(inflated=1))["ok"]
    assert moat_check.compare(_baseline(inflated=1), _run(inflated=1))["ok"]


def test_missing_baseline_advisor_fails():
    v = moat_check.compare(_baseline(extra_adv="sun-tzu"), _run())
    assert not v["ok"] and any("sun-tzu" in f for f in v["failures"])


def test_custom_tolerances_override_defaults():
    v = moat_check.compare(_baseline(0.20), _run(mis=0.26), {"misapply_pp": 0.10})
    assert v["ok"]
    v2 = moat_check.compare(_baseline(0.20), _run(mis=0.22), {"misapply_pp": 0.01})
    assert not v2["ok"]


# ───────────────────────── compare: warnings (не валят) ──────────────────────

def test_judge_model_mismatch_warns_not_fails():
    v = moat_check.compare(_baseline(), _run(model="gemma3:27b"))
    assert v["ok"] and any("модель судьи" in w for w in v["warnings"])


def test_prompt_hash_mismatch_warns():
    v = moat_check.compare(_baseline(), _run(hashes={"judge_prompt": "XXX", "rubric": "bbb"}))
    assert v["ok"] and any("промпт" in w for w in v["warnings"])


def test_corpus_hash_mismatch_warns():
    v = moat_check.compare(_baseline(), _run(corpus="OTHER"))
    assert v["ok"] and any("пересобран" in w for w in v["warnings"])


def test_new_advisor_in_run_warns():
    run = _run()
    run["advisors"]["naval"] = run["advisors"]["machiavelli"]
    v = moat_check.compare(_baseline(), run)
    assert v["ok"] and any("naval" in w for w in v["warnings"])


# ───────────────────────── хэши/батарея ──────────────────────────────────────

def test_prompt_hash_stable_and_sensitive(monkeypatch):
    import relevance_judge
    h1 = moat_check.prompt_hash()
    assert h1 == moat_check.prompt_hash()              # детерминизм
    assert set(h1) == {"judge_prompt", "rubric"}
    monkeypatch.setattr(relevance_judge, "_JUDGE_PROMPT",
                        relevance_judge._JUDGE_PROMPT + "X")
    h2 = moat_check.prompt_hash()
    assert h2["judge_prompt"] != h1["judge_prompt"]    # порча промпта видна
    assert h2["rubric"] == h1["rubric"]


def test_battery_advisors_requires_all_three(tmp_path):
    """В батарею входит только советник с корпусом+камуфляжем+golden — здесь ни одного."""
    (tmp_path / "advisors" / "ghost").mkdir(parents=True)
    assert moat_check.battery_advisors(str(tmp_path)) == []


def test_battery_advisors_discovers_when_all_three_present(tmp_path, monkeypatch):
    """sun-tzu-кейс: корпус + замороженный камуфляж + локальный golden (retrieval.en)
    → советник входит в батарею автоматически, без ручного списка."""
    adv = tmp_path / "advisors" / "sun-tzu"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text('{"text": "chunk"}\n', encoding="utf-8")
    scripts = tmp_path / "scripts"
    (scripts / "moat_battery").mkdir(parents=True)
    (scripts / "golden").mkdir()
    (scripts / "moat_battery" / "sun-tzu.camouflage.jsonl").write_text(
        '{"q": "ooc"}\n', encoding="utf-8")
    (scripts / "golden" / "sun-tzu.retrieval.en.jsonl").write_text(
        '{"q": "ans", "anchor": "chunk", "ref": "I.1"}\n', encoding="utf-8")
    monkeypatch.setattr(moat_check, "HERE", str(scripts))
    monkeypatch.setattr(moat_check, "BATTERY_DIR", str(scripts / "moat_battery"))
    got = moat_check.battery_advisors(str(tmp_path))
    assert [os.path.basename(p) for p in got] == ["sun-tzu"]


# ───────────────────────── run_battery на сеамах ─────────────────────────────

def _mk_battery_advisor(tmp_path):
    adv = tmp_path / "advisors" / "machiavelli"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text(
        json.dumps({"text": "corpus chunk " * 20, "tier": "P1"}) + "\n", encoding="utf-8")
    return str(adv)


def test_run_battery_assembles_report(tmp_path, monkeypatch):
    adv = _mk_battery_advisor(tmp_path)
    # answerable golden подменяем сеамом _answerable_rows (локальный golden гитигнорен)
    monkeypatch.setattr(moat_check, "_answerable_rows",
                        lambda slug, n, seed: [{"q": f"ans-{i}"} for i in range(n)])
    cite_calls = []

    def fake_cite(advisor_dir, query):
        cite_calls.append(query)
        return {"quotes": []}                          # ров держит: grounded нет

    def fake_retrieve(q, d, k):
        return [{"text": "p", "score": 0.6, "source": "s"}]

    def fake_judge(q, p):
        return 3 if q.startswith("ans-") else 0        # answerable проходят, камуфляж гейтится

    run = moat_check.run_battery([adv], seed=1, n_ans=5, n_samples=1,
                                 cite_fn=fake_cite, retrieve_fn=fake_retrieve,
                                 judge_fn=fake_judge, judge_label=("mock", "m1"))
    m = run["advisors"]["machiavelli"]
    assert m["misapply_rate"] == 0.0
    assert m["coverage"] == 1.0
    assert m["judge_ooc_false_accept"] == 0.0
    assert m["n_camouflage"] == 12                     # замороженный набор целиком
    assert len(cite_calls) == 12
    assert run["meta"]["judge_model"] == "m1" and run["meta"]["seed"] == 1
    assert run["meta"]["corpus_sha256"]["machiavelli"]
    assert set(run["meta"]["hashes"]) == {"judge_prompt", "rubric"}
    inj = run["injection"]
    assert inj["n"] >= 10 and inj["gate_flips"] == 0   # fake_judge не ведётся на инъекции


def test_run_battery_leaky_cite_measured(tmp_path, monkeypatch):
    adv = _mk_battery_advisor(tmp_path)
    monkeypatch.setattr(moat_check, "_answerable_rows", lambda s, n, sd: [{"q": "a"}])
    leaky = lambda advisor_dir, query: {"quotes": [{"text": "t", "marker": "🔵"}]}
    run = moat_check.run_battery([adv], cite_fn=leaky,
                                 retrieve_fn=lambda q, d, k: [],
                                 judge_fn=lambda q, p: 0, n_samples=1)
    assert run["advisors"]["machiavelli"]["misapply_rate"] == 1.0


def test_answerable_sampling_deterministic_by_seed(monkeypatch):
    import eval as _eval
    rows = [{"q": f"g{i}"} for i in range(30)]
    monkeypatch.setattr(_eval, "load_golden", lambda slug, kind: (rows, "path"))
    a = moat_check._answerable_rows("machiavelli", 5, seed=42)
    b = moat_check._answerable_rows("machiavelli", 5, seed=42)
    c = moat_check._answerable_rows("machiavelli", 5, seed=43)
    assert a == b and a != c and len(a) == 5
