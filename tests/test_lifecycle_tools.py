"""Zero-code-edit жизненный цикл из чистого MCP-хоста: тюнинг конфига и подъём FULL-тира — тулами,
без правки файлов и шелла. Стережёт: config_get/set реально пишут board_config.json; ollama_* не
падают и честно сообщают про единственный ручной шаг (установка бинаря)."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from mcp_server import dispatch, list_tools, _config_path


def test_config_set_get_roundtrip_persists(monkeypatch, tmp_path):
    cfg = tmp_path / "board_config.json"
    monkeypatch.setattr("mcp_server._config_path", lambda: str(cfg))
    dispatch("config_set", {"key": "retrieval_mode", "value": "hybrid"})
    assert dispatch("config_get", {"key": "retrieval_mode"})["value"] == "hybrid"
    on_disk = json.load(open(cfg, encoding="utf-8"))      # реально записан в файл
    assert on_disk["retrieval_mode"] == "hybrid"
    r = dispatch("config_get", {})
    assert "retrieval_mode" in r["config"] and "known_keys" in r


def test_config_set_warns_on_unknown_key(monkeypatch, tmp_path):
    monkeypatch.setattr("mcp_server._config_path", lambda: str(tmp_path / "c.json"))
    r = dispatch("config_set", {"key": "frobnicate", "value": 1})
    assert "warning" in r and r["new"] == 1


def test_ollama_status_shape_no_crash():
    r = dispatch("ollama_status", {})
    assert set(r) == {"ollama_running", "bge_m3_present"}   # стабильная форма, без падений


def test_ollama_ensure_reports_manual_when_binary_absent(monkeypatch):
    import mcp_server
    monkeypatch.setattr("setup_full.probe", lambda: {"ollama_running": False, "bge_m3_present": False})
    def _no_binary(*a, **k):
        raise FileNotFoundError("ollama")
    monkeypatch.setattr(mcp_server.subprocess if hasattr(mcp_server, "subprocess") else __import__("subprocess"),
                        "Popen", _no_binary, raising=False)
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", _no_binary)
    r = dispatch("ollama_ensure", {})
    assert r["running"] is False and "manual" in r          # честный единственный ручной шаг


def test_add_source_text_lands_and_sets_tier_then_builds(tmp_path):
    # без шелла: text → sources/ + tier-манифест → pipeline собирает корпус с этим тиром
    adv = str(tmp_path / "adv")
    r = dispatch("add_source", {"advisor_dir": adv,
                 "text": "All warfare is based on deception, the canon repeats.",
                 "basename": "canon", "tier": "P1"})
    assert r["ok"] and r["tier"] == "P1"
    man = json.load(open(os.path.join(adv, "sources", "manifest.json"), encoding="utf-8"))
    assert man[r["source_file"]]["tier"] == "P1"
    # сборка видит источник и проставленный тир → дословная фраза проходит гейт как 🔵
    # (детерминированно через fidelity_check; recall cite зависит от семантики — это не предмет add_source)
    from corpusbuild import pipeline
    pipeline.build(adv)
    fc = dispatch("fidelity_check", {"quote": "All warfare is based on deception",
                                     "advisor_dir": adv})
    assert fc["status"] == "🔵" and fc["verbatim"] is True


def test_add_source_url_uses_fetch_and_strips_gutenberg(monkeypatch, tmp_path):
    import collect_common as cc
    monkeypatch.setattr(cc, "fetch", lambda url, timeout=30:
                        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nReal body text here.\n"
                        "*** END OF THE PROJECT GUTENBERG EBOOK X ***")
    adv = str(tmp_path / "adv2")
    r = dispatch("add_source", {"advisor_dir": adv,
                 "url": "https://www.gutenberg.org/cache/epub/1/pg1.txt"})
    assert r["ok"]
    body = open(os.path.join(adv, "sources", r["source_file"]), encoding="utf-8").read()
    assert "Real body text" in body and "START OF THE PROJECT GUTENBERG" not in body  # boilerplate срезан


def test_add_source_rejects_non_pd_host_without_license(tmp_path):
    r = dispatch("add_source", {"advisor_dir": str(tmp_path / "a3"),
                 "url": "https://example.com/some-copyrighted-book.txt"})
    assert "error" in r and "PD" in r["error"]


def test_add_source_blocks_ssrf_even_with_license(tmp_path):
    # license НЕ должен открывать egress: SSRF-гард срабатывает на внутренний адрес независимо
    r = dispatch("add_source", {"advisor_dir": str(tmp_path / "a4"),
                 "url": "http://127.0.0.1:11434/api/tags", "license": "public-domain"})
    assert "error" in r and "SSRF" in r["error"]            # loopback заблокирован, лицензия не помогла


def test_add_source_blocks_path_traversal(tmp_path):
    r = dispatch("add_source", {"advisor_dir": str(tmp_path / "a5"),
                 "path": "../../../../../../etc/passwd"})
    assert "error" in r and ("traversal" in r["error"].lower() or "вне корня" in r["error"])


def test_ssrf_check_passes_public_blocks_private():
    import collect_common as cc
    assert cc.ssrf_check("https://www.gutenberg.org/cache/epub/1/pg1.txt") is None  # публичный → ок
    assert "SSRF" not in (cc.ssrf_check("ftp://x/y") or "")    # схема режется отдельно
    assert cc.ssrf_check("http://127.0.0.1/") and "127.0.0.1" in cc.ssrf_check("http://127.0.0.1/")
    assert cc.ssrf_check("file:///etc/passwd")                 # не-web схема → ошибка


def test_ollama_install_hint_is_platform_aware(monkeypatch):
    import setup_full, mcp_server
    monkeypatch.setattr(setup_full, "_norm_platform", lambda p: "windows")
    assert "ollama.com/download" in mcp_server._ollama_install_hint()   # не захардкожен Mac
    assert set(setup_full.INSTALL_HINTS) >= {"darwin", "linux", "windows"}


def test_lifecycle_tools_registered():
    names = {t["name"] for t in list_tools()}
    assert {"config_get", "config_set", "ollama_status", "ollama_ensure", "ollama_pull",
            "add_source"} <= names
