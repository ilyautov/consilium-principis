"""Zero-code-edit жизненный цикл из чистого MCP-хоста: тюнинг конфига и подъём FULL-тира — тулами,
без правки файлов и шелла. Стережёт: config_get/set реально пишут board_config.json; ollama_* не
падают и честно сообщают про единственный ручной шаг (установка бинаря)."""
import os, sys, json
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import mcp_server
from mcp_server import dispatch, list_tools, _config_path


@pytest.fixture(autouse=True)
def _root_in_tmp(monkeypatch, tmp_path):
    # write-side traversal-гард ограничивает запись корнем репо; тесты пишут советников в tmp_path,
    # поэтому КОРНЕМ на время теста делаем сам tmp_path (advisor_dir под ним → гард пропускает).
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))


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


def test_add_source_provenance_header_not_citable(tmp_path):
    # P0: provenance-хедер `# SOURCE/# FETCHED/# LICENSE` не должен попадать в корпус/цитаты
    adv = str(tmp_path / "adv-hdr")
    dispatch("add_source", {"advisor_dir": adv, "basename": "canon", "tier": "P1",
             "text": "All warfare is based on deception, the canon repeats."})
    from corpusbuild import pipeline, paths
    pipeline.build(adv)
    corpus = open(paths.corpus_path(adv), encoding="utf-8").read()
    assert "# SOURCE" not in corpus and "FETCHED" not in corpus and "LICENSE" not in corpus
    # тело — по-прежнему 🔵, метаданные источника — нет
    assert dispatch("fidelity_check", {"quote": "All warfare is based on deception",
                                       "advisor_dir": adv})["status"] == "🔵"
    assert dispatch("fidelity_check", {"quote": "SOURCE FETCHED LICENSE",
                                       "advisor_dir": adv})["status"] != "🔵"


def test_add_source_write_traversal_blocked(monkeypatch, tmp_path):
    # P0: advisor_dir вне корня репо запрещён (write-side traversal). Корень = tmp_path (autouse),
    # значит путь ВЫШЕ него должен быть отбит.
    outside = str(tmp_path.parent / "escape-advisor")
    r = dispatch("add_source", {"advisor_dir": outside, "text": "x", "tier": "P1"})
    assert "error" in r and "traversal" in r["error"].lower()


def test_build_write_traversal_blocked(tmp_path):
    # гард живёт в _do_build (его зовут и CLI, и фоновый джоб) — тестим там, где он реально стоит
    r = mcp_server._do_build(str(tmp_path.parent / "escape-build"))
    assert "error" in r and "traversal" in r["error"].lower()


def test_ingest_telegram_handle_sanitized():
    import ingest_telegram as itg
    assert itg._safe_handle("@my_channel") == "my_channel"
    assert itg._safe_handle("evil/../../x?a=1") == "evilxa1"    # слэши/спецсимволы срезаны
    import pytest as _pt
    with _pt.raises(ValueError):
        itg._safe_handle("@@@")                                  # пусто после чистки → отказ


def test_instructions_have_antiinjection_rule0():
    import mcp_server
    ins = mcp_server.INSTRUCTIONS
    assert "БЕЗОПАСНОСТЬ ВЫШЕ ВСЕГО" in ins and "ЯВНОЙ просьбе" in ins  # Rule 0 анти-инъекция


def test_short_quote_not_blue(tmp_path):
    # P1: одиночное общее слово дословно совпадёт, но 🔵 для него бессмысленно → 🟡 (порог длины)
    adv = str(tmp_path / "adv-short")
    dispatch("add_source", {"advisor_dir": adv, "basename": "c", "tier": "P1",
             "text": "The discipline of strategy rewards patience."})
    from corpusbuild import pipeline
    pipeline.build(adv)
    assert dispatch("fidelity_check", {"quote": "the", "advisor_dir": adv})["status"] != "🔵"
    assert dispatch("fidelity_check", {"quote": "discipline of strategy",
                                       "advisor_dir": adv})["status"] == "🔵"   # осмысленная — 🔵


def test_ollama_pull_rejects_bad_model_name():
    r = dispatch("ollama_pull", {"model": "evil.com/malware:latest"})   # '/' = чужой реестр
    assert r["ok"] is False and "недопустим" in r["error"]


def test_lifecycle_tools_registered():
    names = {t["name"] for t in list_tools()}
    assert {"config_get", "config_set", "ollama_status", "ollama_ensure", "ollama_pull",
            "add_source"} <= names
