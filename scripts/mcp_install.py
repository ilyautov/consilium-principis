#!/usr/bin/env python3
"""Safely connect Consilium to Claude Desktop's local MCP configuration."""
from __future__ import annotations

from datetime import datetime, timezone
import glob
import json
import os
import re
import shutil
import sys
import time

from file_atomic import atomic_write_json

NAME = "consilium-principis"
_CONFIG_NAME = "claude_desktop_config.json"
_SECRET_ARGUMENT = re.compile(
    r"(?:api[_-]?key|token|secret|password|passwd|authorization|credential)", re.IGNORECASE
)


def config_path(platform=None, home=None, appdata=None):
    """Return the classic Claude Desktop configuration path for *platform*."""
    platform = platform or sys.platform
    home = home or os.path.expanduser("~")
    if platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Claude", _CONFIG_NAME)
    if platform.startswith("win"):
        base = appdata or os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(base, "Claude", _CONFIG_NAME)
    return os.path.join(home, ".config", "Claude", _CONFIG_NAME)


def _dedupe_paths(paths):
    seen = set()
    result = []
    for path in paths:
        normalized = os.path.normcase(os.path.normpath(path))
        if normalized not in seen:
            seen.add(normalized)
            result.append(path)
    return result


def windows_config_paths(appdata=None, localappdata=None, home=None, glob_fn=None):
    """Return classic and Microsoft Store Claude Desktop configuration candidates."""
    home = home or os.path.expanduser("~")
    appdata = appdata or os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    localappdata = (localappdata or os.environ.get("LOCALAPPDATA")
                    or os.path.join(home, "AppData", "Local"))
    glob_fn = glob_fn or glob.glob
    classic = os.path.join(appdata, "Claude", _CONFIG_NAME)
    store_pattern = os.path.join(
        localappdata, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude", _CONFIG_NAME
    )
    return _dedupe_paths([classic, *glob_fn(store_pattern)])


def config_paths(platform=None, home=None, appdata=None, localappdata=None, glob_fn=None):
    """Return all configuration candidates for a platform, in deterministic order."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        return windows_config_paths(
            appdata=appdata, localappdata=localappdata, home=home, glob_fn=glob_fn
        )
    return [config_path(platform=platform, home=home, appdata=appdata)]


def install_record_path(home=None):
    """Return the user-local, secret-free MCP installation record location."""
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".consilium", "last_mcp_install.json")


def server_command():
    """Return (interpreter, [absolute mcp_server.py path])."""
    server = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    return sys.executable, [server]


def merge_entry(cfg, command, args, name=NAME):
    """Return ``(new_config, changed)`` without changing neighbouring MCP servers."""
    cfg = dict(cfg or {})
    servers = dict(cfg.get("mcpServers") or {})
    entry = {"command": command, "args": list(args)}
    if servers.get(name) == entry:
        return cfg, False
    servers[name] = entry
    cfg["mcpServers"] = servers
    return cfg, True


def _read_config(config_file):
    if not os.path.isfile(config_file):
        return None, {}
    try:
        with open(config_file, encoding="utf-8") as handle:
            return None, json.load(handle)
    except Exception as exc:
        return {"ok": False, "reason": "bad_json", "path": config_file, "error": str(exc)}, None


def _backup_config(config_file):
    if not os.path.isfile(config_file):
        return None
    backup = config_file + ".bak." + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config_file, backup)
    return backup


def _safe_args(args):
    """Redact values that follow or embed a conventional secret-bearing argument name."""
    safe = []
    redact_next = False
    for argument in args:
        text = str(argument)
        if redact_next:
            safe.append("[REDACTED]")
            redact_next = False
        elif "=" in text and _SECRET_ARGUMENT.search(text.split("=", 1)[0]):
            safe.append(text.split("=", 1)[0] + "=[REDACTED]")
        else:
            safe.append(text)
            redact_next = text.startswith("-") and bool(_SECRET_ARGUMENT.search(text))
    return safe


def _available_targets(paths, explicit):
    """Avoid treating an absent classic Windows directory as a Store install failure."""
    if explicit:
        return paths
    existing = [path for path in paths if os.path.isdir(os.path.dirname(path))]
    return existing or paths[:1]


def _result(ok, targets, changed, backups, **extra):
    result = {
        "ok": ok,
        "changed": changed,
        "path": targets[0] if targets else None,
        "paths": list(targets),
        "backup": backups[0] if backups else None,
        "backups": list(backups),
    }
    result.update(extra)
    return result


def install(config_file=None, command=None, args=None, do_backup=True, create_dir=False,
            dry_run=False, platform=None, home=None, appdata=None, localappdata=None,
            glob_fn=None, record_path=None):
    """Merge the server into one explicit or several discovered host configurations.

    Existing callers can keep passing one ``config_file``.  Discovery is only used when
    it is omitted; records are written atomically only after every target succeeds.
    """
    platform = platform or sys.platform
    explicit = config_file is not None
    targets = [config_file] if explicit else config_paths(
        platform=platform, home=home, appdata=appdata, localappdata=localappdata, glob_fn=glob_fn
    )
    targets = _available_targets(_dedupe_paths(targets), explicit)
    if command is None:
        command, args = server_command()
    args = list(args or [])
    record_path = record_path or install_record_path(home=home)

    prepared = []
    for target in targets:
        directory = os.path.dirname(target)
        if not os.path.isdir(directory) and not create_dir:
            return _result(False, [target], False, [], reason="no_config_dir",
                           hint="Claude Desktop configuration directory was not found. "
                                "Install Claude Desktop or pass mcp-install --config <file>.")
        error, existing = _read_config(target)
        if error:
            return _result(False, [target], False, [], reason=error["reason"], error=error["error"])
        new_config, changed = merge_entry(existing, command, args)
        prepared.append((target, new_config, changed))

    previews = [json.dumps(config, ensure_ascii=False, indent=2) for _, config, _ in prepared]
    if dry_run:
        return _result(True, targets, any(changed for _, _, changed in prepared), [], dry_run=True,
                       preview=previews[0] if previews else "{}", previews=previews)

    backups = []
    changed_any = False
    for target, new_config, changed in prepared:
        if not changed:
            continue
        directory = os.path.dirname(target)
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        if do_backup:
            backup = _backup_config(target)
            if backup:
                backups.append(backup)
        atomic_write_json(target, new_config, ensure_ascii=False, indent=2)
        changed_any = True

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server_name": NAME,
        "platform": platform,
        "paths": targets,
        "command": str(command),
        "args": _safe_args(args),
    }
    atomic_write_json(record_path, record, ensure_ascii=False, indent=2)
    return _result(True, targets, changed_any, backups,
                   note="already connected (idempotent)",
                   restart="Completely quit Claude Desktop and open it again.")
