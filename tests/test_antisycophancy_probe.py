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
