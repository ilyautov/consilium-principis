import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_selfdoc as g

def test_extract_tools_has_status_and_refs():
    tools = g.extract_tools()
    names = {t["name"] for t in tools}
    assert "fidelity_check" in names
    ft = next(t for t in tools if t["name"] == "fidelity_check")
    assert ft["description"] and isinstance(ft["input_schema"], dict)
    assert ft["status"] in ("surfaced", "internal")
    cv = next(t for t in tools if t["name"] == "catalog_verify")
    assert cv["status"] == "internal"

def test_extract_rules_covers_zero_to_fourteen():
    rules = g.extract_rules()
    ns = [r["n"] for r in rules]
    assert ns == sorted(ns)
    assert set(range(0, 15)).issubset(set(ns))
    assert all(r["title"] and r["text"] for r in rules)

def test_extract_recipes_roundtrips():
    recs = g.extract_recipes()
    assert any(r["id"] == "calibrate" for r in recs)
    assert all({"id", "title", "short", "triggers", "does", "reads"} <= set(r.keys()) for r in recs)
