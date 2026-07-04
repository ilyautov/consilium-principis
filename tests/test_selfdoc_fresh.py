import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_selfdoc as g

ROOT = os.path.join(os.path.dirname(__file__), "..")
IDX = os.path.join(ROOT, "docs", "selfdoc", "index.json")

def _committed():
    return json.load(open(IDX, encoding="utf-8"))

def test_index_exists():
    assert os.path.exists(IDX), "нет docs/selfdoc/index.json — запусти scripts/gen_selfdoc.py"

def test_every_tool_in_index():
    import mcp_server as m
    idx_names = {t["name"] for t in _committed()["tools"]}
    assert set(m.TOOLS) == idx_names, "index.json отстал от TOOLS — пересобери gen_selfdoc.py"

def test_every_rule_captured():
    live = {r["n"] for r in g.extract_rules()}
    committed = {r["n"] for r in _committed()["rules"]}
    assert live == committed, "правила INSTRUCTIONS изменились — пересобери индекс"

def test_meta_counts_match_committed_lists():
    idx = _committed()
    assert idx["meta"]["tool_count"] == len(idx["tools"])
    assert idx["meta"]["rule_count"] == len(idx["rules"])
    assert idx["meta"]["recipe_count"] == len(idx["recipes"])

def test_regenerated_index_matches_committed():
    fresh = g.build_index(root=ROOT)
    committed = _committed()
    assert fresh == committed, "index.json дрейфит от кода — запусти scripts/gen_selfdoc.py и закоммить"

def test_manual_matches_committed():
    import build_manual as bm
    committed = open(os.path.join(ROOT, "docs", "MANUAL.md"), encoding="utf-8").read()
    idx = _committed()
    narr = bm._load_narrative(ROOT)
    rebuilt = bm.assemble(idx, narr)
    assert rebuilt == committed, "docs/MANUAL.md дрейфит — запусти scripts/build_manual.py и закоммить"
