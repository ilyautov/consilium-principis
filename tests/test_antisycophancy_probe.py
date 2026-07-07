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
