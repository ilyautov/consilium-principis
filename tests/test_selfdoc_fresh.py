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


import re

def test_narrative_counters_fresh():
    """Рукописные narrative/*.md не протухают по счётчикам: H6 показал, что
    test_manual_matches_committed проверяет ВОСПРОИЗВОДИМОСТЬ генерации, не АКТУАЛЬНОСТЬ
    нарратива (MANUAL нёс «правила 0–14» при живых 0–17, и сьют был зелёный)."""
    idx = _committed()
    rule_max = max(r["n"] for r in idx["rules"])
    tool_n = idx["meta"]["tool_count"]
    narr_dir = os.path.join(ROOT, "docs", "selfdoc", "narrative")
    for fn in sorted(os.listdir(narr_dir)):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(narr_dir, fn), encoding="utf-8").read()
        for m in re.finditer(r"правил[а-я]*\s+0\s*[–—-]\s*(\d+)", text):
            assert int(m.group(1)) == rule_max, \
                "%s: «правила 0–%s» протухло (живых 0–%d)" % (fn, m.group(1), rule_max)
        for m in re.finditer(r"\b(\d+)\s*тул(?:ов|а)?\b", text):
            assert int(m.group(1)) == tool_n, \
                "%s: «%s тулов» протухло (живых %d)" % (fn, m.group(1), tool_n)
