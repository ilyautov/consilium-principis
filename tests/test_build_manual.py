import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_manual as b

def test_assemble_has_three_layers_and_reference(tmp_path):
    idx = {"meta": {"tool_count": 1, "rule_count": 1, "recipe_count": 0, "script_count": 1,
                    "test_count": 0, "glossary_count": 1},
           "tools": [{"name": "fidelity_check", "description": "гейт", "input_schema": {}, "status": "surfaced", "referenced_in": ["rule:5"]}],
           "rules": [{"n": 5, "title": "КОНТУР ВЕРНОСТИ", "text": "🔵 ставь только..."}],
           "recipes": [], "scripts": [{"path": "scripts/mcp_server.py", "subsystem": "mcp", "doc": "MCP сервер"}],
           "tests": [], "glossary": [{"term": "Consilium", "definition": "совет"}]}
    narr = {"00-overview.md": "# Обзор\nЛичный совет.", "10-moat.md": "# Моат\n🔵🟢🟡📐",
            "20-firewall.md": "# Firewall\nprivate↔public", "30-architecture.md": "# Архитектура\n5 частей",
            "40-extend.md": "# Как расширять\nдобавь тул"}
    md = b.assemble(idx, narr)
    assert "## Слой 1" in md and "## Слой 2" in md and "## Слой 3" in md
    assert "fidelity_check" in md
    assert "КОНТУР ВЕРНОСТИ" in md
    assert "Consilium" in md
    assert "сгенерирован" in md.lower()

def test_build_writes_manual(tmp_path):
    out = tmp_path / "MANUAL.md"
    b.build(root=os.path.join(os.path.dirname(__file__), ".."), out_path=str(out), pdf=False)
    assert out.exists() and "## Слой 1" in out.read_text(encoding="utf-8")
