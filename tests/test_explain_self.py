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
