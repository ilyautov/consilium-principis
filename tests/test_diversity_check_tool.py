import os, sys, json
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server

PERSONA = "---\nname: %s\nlenses: [%s]\ndomains: [%s]\n---\nbody\n"

def _mk_advisors(root):
    specs = [("a1", "compounding, judgment-over-effort", "startups"),
             ("a2", "compounding, judgment-over-effort", "startups"),
             ("b1", "memento-mori, via-negativa", "ethics")]
    for slug, lenses, domains in specs:
        d = root / "advisors" / slug
        d.mkdir(parents=True)
        (d / "persona.md").write_text(PERSONA % (slug, lenses, domains), encoding="utf-8")

def test_diversity_tool_flags_echo_chamber(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    _mk_advisors(tmp_path)
    out = mcp_server.dispatch("diversity_check",
                              {"advisor_dirs": ["advisors/a1", "advisors/a2"]})
    assert out["verdict"] == "echo_chamber"
    assert out["diversity"] < 0.5
    assert out["pairs"][0]["flag"] == "dup"

def test_diversity_tool_healthy_board(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    _mk_advisors(tmp_path)
    out = mcp_server.dispatch("diversity_check",
                              {"advisor_dirs": ["advisors/a1", "advisors/b1"]})
    assert out["verdict"] in ("ok", "overlap")
    assert out["diversity"] >= 0.5

def test_diversity_tool_traversal_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    _mk_advisors(tmp_path)
    out = mcp_server.dispatch("diversity_check",
                              {"advisor_dirs": ["advisors/a1", "/etc"]})
    assert "error" in out
