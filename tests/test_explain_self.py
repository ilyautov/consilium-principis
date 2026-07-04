import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import selfdoc_query as q
import mcp_server as m

ROOT = os.path.join(os.path.dirname(__file__), "..")

def test_overview_returns_sections():
    r = q.explain(None, root=ROOT)
    assert r["kind"] == "self_explanation" and r["sections"]

def test_tool_topic():
    r = q.explain("tool:fidelity_check", root=ROOT)
    assert any("fidelity_check" in s["body"] or "fidelity_check" in s["title"] for s in r["sections"])
    assert r["sections"][0]["source_ref"]

def test_rule_topic():
    r = q.explain("rule:5", root=ROOT)
    assert r["sections"] and "5" in r["sections"][0]["source_ref"]

def test_concept_and_term():
    assert q.explain("concept:moat", root=ROOT)["sections"]
    assert q.explain("term:Consilium", root=ROOT)["sections"]

def test_unknown_topic_failclosed_with_suggestions():
    r = q.explain("tool:no_such_tool_xyz", root=ROOT)
    assert r["sections"] == [] and r["suggestions"]

def test_freetext_bestmatch():
    r = q.explain("моат", root=ROOT)
    assert r["sections"] or r["suggestions"]

def test_dispatch_wired():
    assert "explain_self" in m.TOOLS
    out = m.dispatch("explain_self", {"topic": "overview"})
    assert out["kind"] == "self_explanation"

def test_nonstring_topic_no_crash():
    for bad in (123, True, [1, 2], {"a": 1}):
        r = q.explain(bad, root=ROOT)
        assert r["kind"] == "self_explanation"   # не падает

def test_malformed_index_failclosed(tmp_path):
    import json as _json
    d = tmp_path / "docs" / "selfdoc"
    d.mkdir(parents=True)
    (d / "narrative").mkdir()
    # валидный JSON, но без секций meta/tools/glossary/rules
    (d / "index.json").write_text(_json.dumps({"recipes": []}), encoding="utf-8")
    for topic in (None, "", "моат", "term:x", "rule:5", "tool:fidelity_check"):
        r = q.explain(topic, root=str(tmp_path))
        assert r["kind"] == "self_explanation"       # fail-closed, не KeyError
        assert isinstance(r["sections"], list) and isinstance(r["suggestions"], list)

def test_tool_hit_without_referenced_in_no_crash(tmp_path):
    import json as _json
    d = tmp_path / "docs" / "selfdoc"; d.mkdir(parents=True); (d / "narrative").mkdir()
    idx = {"meta": {"tool_count": 1, "rule_count": 0, "recipe_count": 0, "script_count": 0, "test_count": 0, "glossary_count": 0},
           "tools": [{"name": "foo", "description": "d", "input_schema": {}, "status": "surfaced"}],  # НЕТ referenced_in
           "rules": [], "recipes": [], "scripts": [], "tests": [], "glossary": []}
    (d / "index.json").write_text(_json.dumps(idx), encoding="utf-8")
    r = q.explain("tool:foo", root=str(tmp_path))
    assert r["kind"] == "self_explanation" and r["sections"]   # не KeyError на referenced_in
