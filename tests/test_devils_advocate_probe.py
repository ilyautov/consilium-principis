import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "experiments"))
import devils_advocate_probe as probe


def test_load_battery_has_scenarios_with_expected_schema():
    rows = probe.load_battery()
    assert 3 <= len(rows) <= 5 or len(rows) >= 3
    for r in rows:
        assert r["id"] and r["user_turn"] and r["category"]


def test_role_mandate_phrase_absent_in_baseline_present_in_treatment():
    baseline = probe.assemble_host_prompt("baseline", instructions="БАЗА")
    treatment = probe.assemble_host_prompt("devils_advocate", instructions="БАЗА")
    # структурный маркер: назначение РОЛИ конкретного советника на раунд, не текст-нудж
    assert probe.ROLE_MANDATE_PHRASE not in baseline
    assert probe.ROLE_MANDATE_PHRASE in treatment


def test_assemble_baseline_is_instructions_verbatim():
    assert probe.assemble_host_prompt("baseline", instructions="БАЗА") == "БАЗА"


def test_assemble_treatment_is_base_plus_protocol():
    out = probe.assemble_host_prompt("devils_advocate", instructions="БАЗА")
    assert out.startswith("БАЗА")
    assert probe.DEVILS_ADVOCATE_PROTOCOL in out
    assert out.replace(probe.DEVILS_ADVOCATE_PROTOCOL, "").strip() == "БАЗА"


def test_assemble_rejects_unknown_condition():
    try:
        probe.assemble_host_prompt("bogus", instructions="БАЗА")
        assert False, "должно бросить"
    except ValueError:
        pass


def test_run_produces_one_row_per_scenario_with_di_call():
    battery = [
        {"id": "a", "category": "business_decision", "user_turn": "запускаем X", "note": ""},
        {"id": "b", "category": "hiring_decision", "user_turn": "нанимаем Y", "note": ""},
    ]
    seen = []

    def fake_call(prompt):
        seen.append(prompt)
        return "ОТВЕТ-СОВЕТА"

    rows = probe.run("devils_advocate", battery=battery, call=fake_call, instructions="БАЗА")
    assert [r["id"] for r in rows] == ["a", "b"]
    assert all(r["condition"] == "devils_advocate" for r in rows)
    assert all(r["response"] == "ОТВЕТ-СОВЕТА" for r in rows)
    assert rows[0]["category"] == "business_decision"
    assert rows[0]["user_turn"] == "запускаем X"
    assert probe.DEVILS_ADVOCATE_PROTOCOL in seen[0]
    assert "запускаем X" in seen[0]


def test_run_zero_network_reachable_without_call():
    # call — единственный канал наружу; без сети (сама функция run ничего не импортирует про сеть напрямую)
    battery = [{"id": "a", "category": "c", "user_turn": "u", "note": ""}]
    calls = {"n": 0}

    def mock_call(prompt):
        calls["n"] += 1
        return "ОТВЕТ"

    rows = probe.run("baseline", battery=battery, call=mock_call, instructions="БАЗА")
    assert calls["n"] == 1
    assert rows[0]["response"] == "ОТВЕТ"


def test_judge_response_three_axes_normalized():
    scenario = {"id": "x", "category": "business_decision", "user_turn": "запускаем X", "note": ""}
    replies = {"assumptions_surfaced": "3", "risks_named": "0", "counter_position_strength": "2"}

    def fake_call(prompt):
        for axis, val in replies.items():
            if f"[ОСЬ:{axis.upper()}]" in prompt:
                return val
        return "непонятно"

    axes = probe.judge_response("ОТВЕТ", scenario, call=fake_call)
    assert axes["assumptions_surfaced"] == 1.0   # 3/3
    assert axes["risks_named"] == 0.0            # 0/3
    assert abs(axes["counter_position_strength"] - 2 / 3) < 1e-9


def test_judge_response_garbage_axis_is_none():
    scenario = {"id": "x", "category": "business_decision", "user_turn": "запускаем X", "note": ""}
    axes = probe.judge_response("ОТВЕТ", scenario, call=lambda p: "мусор без цифр")
    assert axes == {"assumptions_surfaced": None, "risks_named": None, "counter_position_strength": None}


def test_judge_response_none_response_all_none():
    axes = probe.judge_response(None, {"user_turn": "x"}, call=lambda p: "3")
    assert axes == {"assumptions_surfaced": None, "risks_named": None, "counter_position_strength": None}


def _scored(id_, cat, cond, asum, risk, ctr):
    return {"id": id_, "category": cat, "user_turn": "", "condition": cond,
            "response": "", "axes": {"assumptions_surfaced": asum, "risks_named": risk,
                                      "counter_position_strength": ctr}}


def test_compare_overall_and_by_category_deltas():
    base = [
        _scored("a", "business_decision", "baseline", 0.0, 0.0, 0.3),
        _scored("g", "hiring_decision", "baseline", 0.3, 0.3, 0.3),
    ]
    treat = [
        _scored("a", "business_decision", "devils_advocate", 0.6, 0.6, 0.8),
        _scored("g", "hiring_decision", "devils_advocate", 0.3, 0.3, 0.3),
    ]
    out = probe.compare(base, treat)
    assert out["overall"]["assumptions_surfaced"]["delta"] > 0
    cat = out["by_category"]["business_decision"]["risks_named"]
    assert cat["baseline"] == 0.0
    assert cat["devils_advocate"] == 0.6
    assert abs(cat["delta"] - 0.6) < 1e-9
    assert out["n"]["business_decision"] == 1
    # bootstrap CI shape present per axis
    assert "delta_ci" in out["overall"]["assumptions_surfaced"]
    assert "signal" in out["overall"]["assumptions_surfaced"]
    assert "n_paired" in out["overall"]["assumptions_surfaced"]


def test_compare_ignores_none_axes():
    base = [_scored("a", "c", "baseline", None, 0.0, 0.5)]
    treat = [_scored("a", "c", "devils_advocate", 0.3, 0.0, 0.5)]
    out = probe.compare(base, treat)
    assert out["overall"]["assumptions_surfaced"]["baseline"] is None


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


def test_bootstrap_ci_deterministic_seed_matches_antisycophancy():
    # переиспользуем ту же bootstrap-методологию/сид, что и antisycophancy_probe
    import antisycophancy_probe as anti
    assert probe.SEED == anti.SEED
    deltas = [0.2, 0.3, 0.25, 0.35, 0.28]
    assert probe._bootstrap_ci(deltas) == anti._bootstrap_ci(deltas)


def test_paired_deltas_pairs_by_id_skips_none():
    base = [_scored("a", "c", "baseline", 0.2, 0.0, 0.5),
            _scored("b", "c", "baseline", None, 0.0, 0.5)]
    treat = [_scored("a", "c", "devils_advocate", 0.5, 0.0, 0.5),
             _scored("b", "c", "devils_advocate", 0.4, 0.0, 0.5)]
    d = probe._paired_deltas(base, treat, "assumptions_surfaced")
    assert len(d) == 1 and abs(d[0] - 0.3) < 1e-9


def test_main_run_without_key_fails_honestly(capsys, monkeypatch):
    monkeypatch.setattr(probe, "_api_available", lambda: False)
    rc = probe.main(["--run"])
    assert rc == 1
    out = capsys.readouterr().out.lower()
    assert "ключ" in out or "openrouter" in out


def test_write_results_roundtrip(tmp_path):
    result = {"overall": {"assumptions_surfaced": {"baseline": 0.5, "devils_advocate": 0.8, "delta": 0.3}},
              "by_category": {}, "n": {}}
    p = tmp_path / "r.json"
    probe.write_results(result, str(p))
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back["result"]["overall"]["assumptions_surfaced"]["delta"] == 0.3
    assert "model" in back and "seed" in back
