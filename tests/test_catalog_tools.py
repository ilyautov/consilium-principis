import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server

def test_catalog_list_tool_registered_and_returns_figures():
    assert "catalog_list" in mcp_server.TOOLS
    out = mcp_server.dispatch("catalog_list", {})
    assert isinstance(out.get("figures"), list)
    assert any(f["id"] == "marcus-aurelius" for f in out["figures"])

def test_catalog_preview_tool_uses_fetch(monkeypatch):
    raw = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nТекст.\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    monkeypatch.setattr("collect_common.fetch", lambda url, **k: raw)
    out = mcp_server.dispatch("catalog_preview", {"ref": "marcus-aurelius"})
    assert out["kind"] == "pd_preview" and out["figure"] == "Марк Аврелий"

def test_catalog_search_tool(monkeypatch):
    gutendex = json.dumps({"results": [{"id": 3800, "title": "Ethics", "authors": [{"name": "Spinoza"}],
        "formats": {"text/plain; charset=utf-8": "https://www.gutenberg.org/files/3800/3800-0.txt"}}]})
    monkeypatch.setattr("collect_common.fetch", lambda url, **k: gutendex)
    out = mcp_server.dispatch("catalog_search", {"author": "Spinoza"})
    assert out["ok"] and out["candidates"][0]["gutenberg_id"] == 3800
