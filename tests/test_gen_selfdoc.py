import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_selfdoc as g

def test_extract_tests_graceful_without_tests_dir(tmp_path):
    # В установленном скилле tests/ не шипуется. explain_self советует запустить gen_selfdoc при
    # пустом индексе — extract_tests не должен падать FileNotFoundError, а вернуть [] (graceful).
    assert g.extract_tests(root=str(tmp_path)) == []


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

def test_scripts_inventory_module_level():
    scripts = g.extract_scripts()
    paths = {s["path"] for s in scripts}
    assert any(p.endswith("mcp_server.py") for p in paths)
    assert any(p.endswith("gen_selfdoc.py") for p in paths)
    s = next(s for s in scripts if s["path"].endswith("mcp_server.py"))
    assert s["subsystem"] and isinstance(s["doc"], str)

def test_tests_inventory():
    tests = g.extract_tests()
    assert any(t["path"].endswith("test_gen_selfdoc.py") for t in tests)

def test_glossary_parsed():
    terms = g.extract_glossary()
    names = {t["term"] for t in terms}
    assert "Consilium" in names
    assert all(t["definition"] for t in terms)

def test_build_index_shape_and_meta():
    idx = g.build_index()
    for k in ("meta", "tools", "rules", "recipes", "scripts", "tests", "glossary"):
        assert k in idx
    assert idx["meta"]["tool_count"] == len(idx["tools"]) > 0
    assert idx["meta"]["rule_count"] == len(idx["rules"])
    assert idx["meta"]["glossary_count"] == len(idx["glossary"])

def test_write_index_roundtrip(tmp_path):
    idx = g.build_index()
    p = tmp_path / "index.json"
    g.write_index(idx, str(p))
    assert json.loads(p.read_text(encoding="utf-8"))["meta"]["tool_count"] == idx["meta"]["tool_count"]

def test_build_index_deterministic():
    # гард Task 8 сверяет регенерацию с коммитом — build_index обязан быть byte-детерминирован
    assert g.build_index() == g.build_index()
