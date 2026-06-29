"""Скриптовое подключение MCP в claude_desktop_config.json. Критично: МЕРДЖ (не затереть соседние
серверы), идемпотентность, бэкап перед правкой внешнего конфига, безопасный отказ на битом JSON."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from mcp_install import config_path, merge_entry, install, server_command, NAME


def test_config_path_per_os():
    assert config_path("darwin", home="/h").endswith(
        "/h/Library/Application Support/Claude/claude_desktop_config.json")
    assert config_path("win32", home="/h", appdata="/AD").endswith(
        "/AD/Claude/claude_desktop_config.json")
    assert config_path("linux", home="/h").endswith("/h/.config/Claude/claude_desktop_config.json")


def test_merge_preserves_other_servers():
    existing = {"mcpServers": {"ollama-bridge": {"command": "x", "args": []}}}
    cfg, changed = merge_entry(existing, "py", ["s.py"])
    assert changed
    assert "ollama-bridge" in cfg["mcpServers"]          # соседи целы
    assert cfg["mcpServers"][NAME] == {"command": "py", "args": ["s.py"]}


def test_merge_is_idempotent():
    cfg, _ = merge_entry({}, "py", ["s.py"])
    cfg2, changed = merge_entry(cfg, "py", ["s.py"])
    assert changed is False                              # второй раз ничего не меняет


def test_install_creates_merges_and_backs_up(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    cfgf.write_text(json.dumps({"mcpServers": {"ozon": {"command": "o", "args": []}}}),
                    encoding="utf-8")
    r = install(str(cfgf), command="py", args=["s.py"])
    assert r["ok"] and r["changed"] and r["backup"]
    saved = json.loads(cfgf.read_text(encoding="utf-8"))
    assert "ozon" in saved["mcpServers"] and NAME in saved["mcpServers"]
    assert os.path.isfile(r["backup"])                  # бэкап реально создан
    # второй прогон — идемпотентен, без изменений
    assert install(str(cfgf), command="py", args=["s.py"])["changed"] is False


def test_install_dry_run_does_not_write(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    r = install(str(cfgf), command="py", args=["s.py"], dry_run=True)
    assert r["dry_run"] and NAME in r["preview"]
    assert not cfgf.exists()                             # dry-run не пишет


def test_install_missing_dir_refuses_without_create(tmp_path):
    r = install(str(tmp_path / "nope" / "c.json"), command="py", args=["s.py"])
    assert r["ok"] is False and r["reason"] == "no_config_dir"


def test_install_bad_json_fails_safe(tmp_path):
    cfgf = tmp_path / "Claude" / "c.json"
    cfgf.parent.mkdir(parents=True)
    cfgf.write_text("{ это не json", encoding="utf-8")
    r = install(str(cfgf), command="py", args=["s.py"])
    assert r["ok"] is False and r["reason"] == "bad_json"


def test_server_command_is_absolute():
    cmd, args = server_command()
    assert os.path.isabs(args[0]) and args[0].endswith("mcp_server.py")
