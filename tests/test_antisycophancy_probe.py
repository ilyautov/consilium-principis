import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "experiments"))
import antisycophancy_probe as probe


def test_load_battery_has_three_categories():
    rows = probe.load_battery()
    assert len(rows) >= 9
    cats = {r["category"] for r in rows}
    assert cats == {"sycophancy_trap", "false_premise", "genuine_consensus"}
    for r in rows:
        assert r["id"] and r["user_turn"] and r["category"]


def test_candidate_no_raw_percent():
    # INSTRUCTIONS форматируется как template % _FEWSHOT_TEXT; сырой % сломал бы будущую вставку.
    assert "%" not in probe.RULE_15_CANDIDATE


def test_assemble_baseline_is_instructions_verbatim():
    assert probe.assemble_host_prompt("baseline", instructions="БАЗА") == "БАЗА"


def test_assemble_treatment_is_base_plus_candidate():
    out = probe.assemble_host_prompt("with_rule15", instructions="БАЗА")
    assert out.startswith("БАЗА")
    assert probe.RULE_15_CANDIDATE in out
    # отличие ровно на блок кандидата (плюс разделитель)
    assert out.replace(probe.RULE_15_CANDIDATE, "").strip() == "БАЗА"


def test_assemble_rejects_unknown_condition():
    try:
        probe.assemble_host_prompt("bogus", instructions="БАЗА")
        assert False, "должно бросить"
    except ValueError:
        pass


def test_run_produces_one_row_per_scenario_with_di_call():
    battery = [
        {"id": "a", "category": "sycophancy_trap", "user_turn": "делаю X", "note": ""},
        {"id": "b", "category": "genuine_consensus", "user_turn": "ротировать ключ?", "note": ""},
    ]
    seen = []

    def fake_call(prompt):
        seen.append(prompt)
        return "ОТВЕТ-СОВЕТА"

    rows = probe.run("with_rule15", battery=battery, call=fake_call, instructions="БАЗА")
    assert [r["id"] for r in rows] == ["a", "b"]
    assert all(r["condition"] == "with_rule15" for r in rows)
    assert all(r["response"] == "ОТВЕТ-СОВЕТА" for r in rows)
    assert rows[0]["category"] == "sycophancy_trap"
    assert rows[0]["user_turn"] == "делаю X"
    # промпт хоста несёт кандидат и обращение юзера
    assert probe.RULE_15_CANDIDATE in seen[0]
    assert "делаю X" in seen[0]


def test_parse_score_clean_and_garbage():
    assert probe._parse_score("2") == 2
    assert probe._parse_score("  0 ") == 0
    assert probe._parse_score("оценка: 3, потому что...") == 3
    assert probe._parse_score("непонятно") is None


def test_judge_response_three_axes_normalized():
    scenario = {"id": "x", "category": "sycophancy_trap", "user_turn": "делаю X", "note": ""}
    replies = {"sycophancy": "3", "theater": "0", "substance": "2"}

    def fake_call(prompt):
        for axis, val in replies.items():
            if f"[ОСЬ:{axis.upper()}]" in prompt:
                return val
        return "непонятно"

    axes = probe.judge_response("ОТВЕТ", scenario, call=fake_call)
    assert axes["sycophancy"] == 1.0   # 3/3
    assert axes["theater"] == 0.0      # 0/3
    assert abs(axes["substance"] - 2 / 3) < 1e-9


def test_judge_response_garbage_axis_is_none():
    scenario = {"id": "x", "category": "false_premise", "user_turn": "уберём моат?", "note": ""}
    axes = probe.judge_response("ОТВЕТ", scenario, call=lambda p: "мусор без цифр")
    assert axes == {"sycophancy": None, "theater": None, "substance": None}


def test_parse_score_reasoning_and_out_of_range():
    assert probe._parse_score("ставлю 3") == 3
    assert probe._parse_score("первая мысль 0, но ставлю 3") is None  # неоднозначно → не угадываем
    assert probe._parse_score("было 3, ставлю 2") is None
    assert probe._parse_score("10") is None
    assert probe._parse_score("-1") is None
    assert probe._parse_score("5") is None


def test_parse_score_non_string_inputs():
    assert probe._parse_score(None) is None
    assert probe._parse_score(3) == 3     # int коэрсится, не падает
    assert probe._parse_score(0) == 0     # 0 не теряется как falsy


def test_judge_response_missing_user_turn_no_crash():
    axes = probe.judge_response("ОТВЕТ", {"id": "x", "category": "c"}, call=lambda p: "1")
    assert abs(axes["sycophancy"] - 1 / 3) < 1e-9


def _scored(id_, cat, cond, syc, th, sub):
    return {"id": id_, "category": cat, "user_turn": "", "condition": cond,
            "response": "", "axes": {"sycophancy": syc, "theater": th, "substance": sub}}


def test_compare_overall_and_by_category_deltas():
    base = [
        _scored("a", "sycophancy_trap", "baseline", 1.0, 0.0, 0.5),
        _scored("g", "genuine_consensus", "baseline", 0.0, 0.0, 1.0),
    ]
    treat = [
        _scored("a", "sycophancy_trap", "with_rule15", 0.4, 0.0, 0.6),
        _scored("g", "genuine_consensus", "with_rule15", 0.0, 0.9, 1.0),  # театр вырос на контроле!
    ]
    out = probe.compare(base, treat)
    # overall sycophancy упала (в среднем)
    assert out["overall"]["sycophancy"]["delta"] < 0
    # театр на genuine_consensus подскочил — детектор театра ловит
    gt = out["by_category"]["genuine_consensus"]["theater"]
    assert gt["baseline"] == 0.0
    assert gt["with_rule15"] == 0.9
    assert gt["delta"] == 0.9
    assert out["n"]["sycophancy_trap"] == 1


def test_compare_ignores_none_axes():
    base = [_scored("a", "false_premise", "baseline", None, 0.0, 0.5)]
    treat = [_scored("a", "false_premise", "with_rule15", 0.3, 0.0, 0.5)]
    out = probe.compare(base, treat)
    # baseline sycophancy = среднее пустого множества → None, дельта не считается
    assert out["overall"]["sycophancy"]["baseline"] is None


def test_write_results_roundtrip(tmp_path):
    result = {"overall": {"sycophancy": {"baseline": 0.5, "with_rule15": 0.2, "delta": -0.3}},
              "by_category": {}, "n": {}}
    p = tmp_path / "r.json"
    probe.write_results(result, str(p))
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back["result"]["overall"]["sycophancy"]["delta"] == -0.3
    assert "model" in back and "seed" in back  # дисциплина moat_check: пин модели/сида


def test_format_table_mentions_axes_and_deltas():
    result = {"overall": {"sycophancy": {"baseline": 0.9, "with_rule15": 0.3, "delta": -0.6},
                          "theater": {"baseline": 0.0, "with_rule15": 0.1, "delta": 0.1},
                          "substance": {"baseline": 0.6, "with_rule15": 0.6, "delta": 0.0}},
              "by_category": {}, "n": {}}
    txt = probe.format_table(result)
    assert "sycophancy" in txt and "theater" in txt and "substance" in txt
    assert "-0.6" in txt


def test_main_run_without_key_fails_honestly(capsys, monkeypatch):
    monkeypatch.setattr(probe, "_api_available", lambda: False)
    rc = probe.main(["--run"])
    assert rc == 1
    out = capsys.readouterr().out.lower()
    assert "ключ" in out or "openrouter" in out


def test_safe_call_swallows_exception():
    def boom(p):
        raise RuntimeError("network")
    assert probe._safe_call(boom, "x") is None
    assert probe._safe_call(lambda p: "ok", "x") == "ok"


def test_run_host_failure_yields_none_response():
    battery = [{"id": "a", "category": "c", "user_turn": "u", "note": ""}]
    def boom(p):
        raise RuntimeError("net")
    rows = probe.run("baseline", battery=battery, call=boom, instructions="БАЗА")
    assert rows[0]["response"] is None


def test_judge_response_none_response_all_none():
    axes = probe.judge_response(None, {"user_turn": "x"}, call=lambda p: "3")
    assert axes == {"sycophancy": None, "theater": None, "substance": None}


def test_default_call_uses_temp_zero_and_model(monkeypatch):
    import llm_local
    captured = {}
    def fake_generate(prompt, model=None, temperature=0.3, timeout=120):
        captured["model"] = model
        captured["temperature"] = temperature
        return "1"
    monkeypatch.setattr(llm_local, "generate", fake_generate)
    probe._default_call("PROMPT")
    assert captured["temperature"] == 0.0
    assert captured["model"] == probe._model_name()


def test_compare_reports_valid_n_per_axis():
    base = [_scored("a", "c", "baseline", 0.5, None, 0.5)]
    treat = [_scored("a", "c", "with_rule15", 0.3, 0.4, 0.5)]
    out = probe.compare(base, treat)
    assert out["overall"]["theater"]["n_baseline"] == 0
    assert out["overall"]["theater"]["n_with_rule15"] == 1


def test_main_run_sets_model_and_backend(monkeypatch):
    monkeypatch.setattr(probe, "_api_available", lambda: True)
    monkeypatch.delenv("LLM_API_MODEL", raising=False)
    monkeypatch.setattr(probe, "_run_live", lambda: 0)
    rc = probe.main(["--run"])
    assert rc == 0
    assert os.environ.get("LLM_API_MODEL")
    assert os.environ.get("LLM_BACKEND") == "openrouter"


def test_bootstrap_ci_none_below_two():
    assert probe._bootstrap_ci([0.5]) is None
    assert probe._bootstrap_ci([]) is None


def test_bootstrap_ci_deterministic_and_brackets_mean():
    deltas = [0.2, 0.3, 0.25, 0.35, 0.28]
    ci1 = probe._bootstrap_ci(deltas)
    ci2 = probe._bootstrap_ci(deltas)
    assert ci1 == ci2  # детерминизм (сид)
    lo, hi = ci1
    m = sum(deltas) / len(deltas)
    assert lo <= m <= hi


def test_paired_deltas_pairs_by_id_skips_none():
    base = [_scored("a", "c", "baseline", 0.2, 0.0, 0.5),
            _scored("b", "c", "baseline", None, 0.0, 0.5)]
    treat = [_scored("a", "c", "with_rule15", 0.5, 0.0, 0.5),
             _scored("b", "c", "with_rule15", 0.4, 0.0, 0.5)]
    d = probe._paired_deltas(base, treat, "sycophancy")
    assert len(d) == 1 and abs(d[0] - 0.3) < 1e-9  # b пропущен (base None); a: 0.5-0.2=0.3 (допуск float)


def test_compare_signal_flag_when_ci_excludes_zero():
    base = [_scored(f"s{i}", "c", "baseline", 0.1, 0.0, 0.5) for i in range(6)]
    treat = [_scored(f"s{i}", "c", "with_rule15", 0.9, 0.0, 0.5) for i in range(6)]
    out = probe.compare(base, treat)
    assert out["overall"]["sycophancy"]["signal"] is True   # все дельты +0.8 → CI не включает 0
    assert out["overall"]["theater"]["signal"] is False     # все дельты 0 → CI включает 0
    assert out["overall"]["sycophancy"]["n_paired"] == 6
