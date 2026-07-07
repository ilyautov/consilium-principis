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
