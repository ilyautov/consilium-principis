"""Скриптовое подключение MCP в claude_desktop_config.json. Критично: МЕРДЖ (не затереть соседние
серверы), идемпотентность, бэкап перед правкой внешнего конфига, безопасный отказ на битом JSON."""
import os, sys, json, shutil, threading
from pathlib import Path
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import board
import mcp_install
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
    record = tmp_path / ".consilium" / "last_mcp_install.json"
    cfgf.parent.mkdir(parents=True)
    cfgf.write_text(json.dumps({"mcpServers": {"ozon": {"command": "o", "args": []}}}),
                    encoding="utf-8")
    r = install(str(cfgf), command="py", args=["s.py"], record_path=str(record))
    assert r["ok"] and r["changed"] and r["backup"]
    saved = json.loads(cfgf.read_text(encoding="utf-8"))
    assert "ozon" in saved["mcpServers"] and NAME in saved["mcpServers"]
    assert os.path.isfile(r["backup"])                  # бэкап реально создан
    # второй прогон — идемпотентен, без изменений
    assert install(str(cfgf), command="py", args=["s.py"], record_path=str(record))["changed"] is False


def test_install_dry_run_does_not_write(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    r = install(str(cfgf), command="py", args=["s.py"], dry_run=True)
    assert r["dry_run"] and NAME in r["preview"]
    assert not cfgf.exists()                             # dry-run не пишет


def test_default_dry_run_does_not_create_mcp_runtime(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    home = tmp_path / "home"

    result = install(str(cfgf), home=str(home), dry_run=True)

    assert result["ok"] is True and result["dry_run"] is True
    assert not (home / ".consilium" / "mcp-runtime").exists()


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


def test_install_copies_versioned_user_runtime_and_does_not_reference_source_checkout(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    home = tmp_path / "home"
    record = home / ".consilium" / "last_mcp_install.json"

    result = install(str(cfgf), home=str(home), record_path=str(record))

    assert result["ok"] is True
    saved = json.loads(cfgf.read_text(encoding="utf-8"))
    entry = saved["mcpServers"][NAME]
    runtime_server = entry["args"][0]
    assert runtime_server.startswith(str(home / ".consilium" / "mcp-runtime"))
    assert os.path.isfile(runtime_server)
    assert os.path.dirname(os.path.dirname(runtime_server)) != os.path.dirname(
        os.path.dirname(os.path.abspath(mcp_install.__file__))
    )
    assert entry["command"] == sys.executable


def test_rerun_moves_config_to_a_new_content_versioned_runtime(tmp_path, monkeypatch):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    home = tmp_path / "home"
    record = home / ".consilium" / "last_mcp_install.json"
    identities = iter(("v1-old-content", "v1-new-content"))
    monkeypatch.setattr(mcp_install, "_runtime_identity", lambda: next(identities))

    first = install(str(cfgf), home=str(home), record_path=str(record))
    first_server = json.loads(cfgf.read_text(encoding="utf-8"))["mcpServers"][NAME]["args"][0]
    Path(first_server).write_text("stale runtime", encoding="utf-8")

    second = install(str(cfgf), home=str(home), record_path=str(record))
    second_server = json.loads(cfgf.read_text(encoding="utf-8"))["mcpServers"][NAME]["args"][0]

    assert first["ok"] and second["ok"] and second["changed"]
    assert first_server != second_server
    assert "stale runtime" not in Path(second_server).read_text(encoding="utf-8")
    assert Path(first_server).read_text(encoding="utf-8") == "stale runtime"


def test_concurrent_installs_preserve_each_servers_entry(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    cfgf.write_text(json.dumps({"mcpServers": {"existing": {"command": "old", "args": []}}}),
                    encoding="utf-8")
    barrier = threading.Barrier(2)
    outcomes = []

    def connect(name):
        barrier.wait()
        outcomes.append(install(str(cfgf), command="py", args=[name],
                                record_path=str(tmp_path / (name + ".json"))))

    first = threading.Thread(target=connect, args=("first.py",))
    second = threading.Thread(target=connect, args=("second.py",))
    first.start(); second.start(); first.join(); second.join()

    assert all(result["ok"] for result in outcomes)
    servers = json.loads(cfgf.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["existing"] == {"command": "old", "args": []}
    # Both clients use the same Consilium key, so a concurrent update must retain one complete entry.
    assert servers[NAME]["args"] in (["first.py"], ["second.py"])


def test_multi_target_failure_reports_per_target_recovery_without_overwriting_record(tmp_path, monkeypatch):
    first = tmp_path / "classic" / "claude_desktop_config.json"
    second = tmp_path / "store" / "claude_desktop_config.json"
    first.parent.mkdir(parents=True); second.parent.mkdir(parents=True)
    original = '{"mcpServers": {"existing": {"command": "old", "args": []}}}\n'
    first.write_text(original, encoding="utf-8")
    monkeypatch.setattr(mcp_install, "config_paths", lambda **_kwargs: [str(first), str(second)])
    real_write = mcp_install.atomic_update_json

    def fail_second(path, *args, **kwargs):
        if path == str(second):
            raise OSError("store replacement failed")
        return real_write(path, *args, **kwargs)

    monkeypatch.setattr(mcp_install, "atomic_update_json", fail_second)
    result = install(command="py", args=["s.py"], platform="win32",
                     record_path=str(tmp_path / "record.json"))

    assert result["ok"] is False
    assert result["reason"] == "write_failed"
    assert result["recovery"][str(first)] == {
        "pre_state": "existing", "status": "rolled_back", "backup": result["backups"][0],
        "action": "restored backup",
    }
    assert first.read_text(encoding="utf-8") == original


def test_multi_target_failure_removes_entry_created_in_absent_first_config(tmp_path, monkeypatch):
    first = tmp_path / "classic" / "claude_desktop_config.json"
    second = tmp_path / "store" / "claude_desktop_config.json"
    first.parent.mkdir(parents=True); second.parent.mkdir(parents=True)
    monkeypatch.setattr(mcp_install, "config_paths", lambda **_kwargs: [str(first), str(second)])
    real_update = mcp_install.atomic_update_json

    def fail_second(path, *args, **kwargs):
        if path == str(second):
            raise OSError("store replacement failed")
        return real_update(path, *args, **kwargs)

    monkeypatch.setattr(mcp_install, "atomic_update_json", fail_second)
    result = install(command="py", args=["s.py"], platform="win32",
                     record_path=str(tmp_path / "record.json"))

    assert result["ok"] is False
    assert result["recovery"][str(first)] == {
        "pre_state": "absent", "status": "rolled_back_entry", "backup": None,
        "action": "removed the newly created MCP entry",
    }
    assert NAME not in json.loads(first.read_text(encoding="utf-8")).get("mcpServers", {})


def test_install_doctor_validates_record_and_stdio_initialize(tmp_path, monkeypatch):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    home = tmp_path / "home"
    record = home / ".consilium" / "last_mcp_install.json"
    installed = install(str(cfgf), home=str(home), record_path=str(record))
    assert installed["ok"]

    class Completed:
        returncode = 0
        stdout = '{"jsonrpc":"2.0","id":"consilium-doctor","result":{"serverInfo":{"name":"consilium-principis"}}}\n'
        stderr = ""

    monkeypatch.setattr(mcp_install.subprocess, "run", lambda *args, **kwargs: Completed())
    result = mcp_install.check_install(record_path=str(record))

    assert result["ok"] is True
    assert result["name"] == "mcp-install"
    assert result["detail"] == "MCP runtime responds to initialize"


def test_install_doctor_reports_timeout_with_recovery(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    server = tmp_path / "runtime" / "scripts" / "mcp_server.py"
    server.parent.mkdir(parents=True)
    server.write_text("", encoding="utf-8")
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {NAME: {"command": sys.executable,
                                                       "args": [str(server)]}}}), encoding="utf-8")
    record.write_text(json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "server_name": NAME,
                                  "platform": "linux", "paths": [str(cfg)],
                                  "command": sys.executable, "args": [str(server)]}), encoding="utf-8")
    def timed_out(*_args, **_kwargs):
        raise mcp_install.subprocess.TimeoutExpired([sys.executable, str(server)], 1)

    monkeypatch.setattr(mcp_install.subprocess, "run", timed_out)
    result = mcp_install.check_install(record_path=str(record), timeout=0.01)

    assert result["ok"] is False
    assert "timed out" in result["detail"]
    assert "mcp-install" in result["recovery"]


def test_windows_paths_include_classic_and_store_configs(tmp_path):
    paths = mcp_install.windows_config_paths(
        appdata=str(tmp_path / "AppData"),
        localappdata=str(tmp_path / "LocalAppData"),
        glob_fn=lambda _: [str(tmp_path / "LocalAppData/Packages/Claude_123/LocalCache/Roaming/Claude/claude_desktop_config.json")],
    )
    assert paths[0].endswith("AppData/Claude/claude_desktop_config.json")
    assert any("Packages/Claude_123" in path for path in paths)


def test_config_paths_deduplicates_windows_discovery(tmp_path):
    classic = tmp_path / "AppData/Claude/claude_desktop_config.json"
    assert mcp_install.config_paths(
        platform="win32",
        appdata=str(tmp_path / "AppData"),
        localappdata=str(tmp_path / "LocalAppData"),
        glob_fn=lambda _: [str(classic), str(classic)],
    ) == [str(classic)]


def test_interrupted_config_replacement_keeps_previous_config_and_backup(tmp_path, monkeypatch):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    previous = '{"mcpServers": {"other": {}}}\n'
    cfgf.write_text(previous, encoding="utf-8")

    def interrupted(*_args, **_kwargs):
        raise OSError("interrupted replacement")

    monkeypatch.setattr(mcp_install, "atomic_update_json", interrupted)
    with pytest.raises(OSError, match="interrupted replacement"):
        install(str(cfgf), command="py", args=["s.py"])

    assert cfgf.read_text(encoding="utf-8") == previous


def test_dry_run_has_zero_config_or_record_side_effects(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    record = tmp_path / ".consilium" / "last_mcp_install.json"

    result = install(str(cfgf), command="py", args=["s.py"], dry_run=True,
                     record_path=str(record))

    assert result["dry_run"] is True
    assert not cfgf.exists()
    assert not record.exists()
    assert not list(cfgf.parent.glob("*.bak.*"))


def test_explicit_path_bypasses_platform_discovery(tmp_path, monkeypatch):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    monkeypatch.setattr(mcp_install, "config_paths",
                        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("discovery used")))

    result = install(str(cfgf), command="py", args=["s.py"], dry_run=True,
                     platform="win32", record_path=str(tmp_path / "record.json"))

    assert result["ok"] is True and result["path"] == str(cfgf)


def test_successful_install_writes_secret_free_record(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    record = tmp_path / ".consilium" / "last_mcp_install.json"

    result = install(str(cfgf), command="py", args=["s.py", "--api-key", "very-secret"],
                     record_path=str(record), platform="linux")

    assert result["ok"] is True and record.is_file()
    text = record.read_text(encoding="utf-8")
    saved = json.loads(text)
    assert set(saved) == {"timestamp", "server_name", "platform", "paths", "command", "args"}
    assert saved["paths"] == [str(cfgf)]
    assert "very-secret" not in text


def test_install_record_redacts_header_and_environment_secret_forms(tmp_path):
    cfgf = tmp_path / "Claude" / "claude_desktop_config.json"
    cfgf.parent.mkdir(parents=True)
    record = tmp_path / ".consilium" / "last_mcp_install.json"
    secrets = ("header-secret", "env-secret", "token-secret")

    result = install(
        str(cfgf),
        command="py",
        args=[
            "s.py", "--verbose", "-H", "Authorization: Bearer header-secret",
            "--env=API_KEY=env-secret", "--token", "token-secret",
        ],
        record_path=str(record),
        platform="linux",
    )

    assert result["ok"] is True
    text = record.read_text(encoding="utf-8")
    assert all(secret not in text for secret in secrets)
    saved = json.loads(text)
    assert saved["args"][:2] == ["s.py", "--verbose"]


def test_failed_multi_target_install_does_not_replace_prior_record(tmp_path, monkeypatch):
    first = tmp_path / "classic" / "claude_desktop_config.json"
    second = tmp_path / "store" / "claude_desktop_config.json"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    second.write_text("{broken", encoding="utf-8")
    record = tmp_path / ".consilium" / "last_mcp_install.json"
    record.parent.mkdir()
    prior = '{"timestamp": "previous"}\n'
    record.write_text(prior, encoding="utf-8")
    monkeypatch.setattr(mcp_install, "config_paths", lambda **_kwargs: [str(first), str(second)])

    result = install(command="py", args=["s.py"], platform="win32", record_path=str(record))

    assert result["ok"] is False and result["reason"] == "bad_json"
    assert record.read_text(encoding="utf-8") == prior


def test_board_reports_all_modified_paths_and_backups(monkeypatch, capsys):
    monkeypatch.setattr(mcp_install, "install", lambda **_kwargs: {
        "ok": True, "changed": True, "path": "classic.json",
        "paths": ["classic.json", "store.json"], "backups": ["classic.bak"],
        "restart": "Restart Claude Desktop.",
    })

    assert board.cmd_mcp_install([]) == 0

    output = capsys.readouterr().out
    assert "classic.json" in output and "store.json" in output and "classic.bak" in output


def test_board_reports_all_paths_for_idempotent_multi_target_install(monkeypatch, capsys):
    monkeypatch.setattr(mcp_install, "install", lambda **_kwargs: {
        "ok": True, "changed": False, "path": "classic.json",
        "paths": ["classic.json", "store.json"], "note": "already connected",
    })

    assert board.cmd_mcp_install([]) == 0

    output = capsys.readouterr().out
    assert "classic.json" in output and "store.json" in output
