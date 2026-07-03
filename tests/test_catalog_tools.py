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

def test_catalog_add_builds_real_corpus_offline(tmp_path, monkeypatch):
    import catalog
    raw = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + ("Добродетель есть знание. " * 60) + \
          "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    sha = catalog.text_sha256(catalog.strip_for_signature(raw))
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "pd_figures.json").write_text(json.dumps({"version": 1, "figures": [
        {"id": "epictetus", "name": "Эпиктет", "seat": "стоик",
         "source": {"platform": "gutenberg", "ref": "45109", "edition": "e",
                    "url": "https://www.gutenberg.org/cache/epub/45109/pg45109.txt",
                    "pd_basis": "PG (US-PD)", "expected": {"sha256": sha}}}]}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr("mcp_server._root", lambda: str(tmp_path))
    monkeypatch.setattr("collect_common.fetch", lambda url, **k: raw)
    out = mcp_server.dispatch("catalog_add", {"ref": "epictetus"})
    assert out["ok"]
    assert (tmp_path / "advisors" / "epictetus" / "build" / "corpus.jsonl").exists()

def test_install_ships_catalog():
    import install
    assert any("catalog" in str(x) for x in install.RUNTIME), "catalog/ не в RUNTIME install.py"

def test_instructions_mention_catalog_flow():
    assert "catalog_preview" in mcp_server.INSTRUCTIONS
    assert "catalog_add" in mcp_server.INSTRUCTIONS
    # порядок consent: превью упоминается ПЕРЕД сборкой
    assert mcp_server.INSTRUCTIONS.index("catalog_preview") < mcp_server.INSTRUCTIONS.index("catalog_add")
