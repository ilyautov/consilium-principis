#!/usr/bin/env python3
"""Safely connect Consilium to Claude Desktop's local MCP configuration."""
from __future__ import annotations

from datetime import datetime, timezone
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from file_atomic import atomic_update_json, atomic_write_json, ensure_private_directory, exclusive_file_lock

NAME = "consilium-principis"
_CONFIG_NAME = "claude_desktop_config.json"
_SECRET_ARGUMENT = re.compile(
    r"(?:api[_-]?key|token|secret|password|passwd|authorization|credential)", re.IGNORECASE
)
_HEADER_OPTIONS = {"-H", "--header"}
_ENVIRONMENT_OPTIONS = {"-e", "--env"}
_RUNTIME_VERSION = "v1"
_RUNTIME_ITEMS = ("scripts", "lenses", "gov_heads.json", "catalog", "recipes.json")
_HANDSHAKE_ID = "consilium-doctor"
_HANDSHAKE_TIMEOUT = 5


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


def runtime_path(home=None, version=_RUNTIME_VERSION):
    """Return the versioned, user-owned MCP runtime location."""
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".consilium", "mcp-runtime", version)


def _source_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _copy_runtime(runtime):
    """Publish a self-contained stdlib-only runtime once; never reference the checkout."""
    server = os.path.join(runtime, "scripts", "mcp_server.py")
    if os.path.isfile(server):
        return runtime
    parent = os.path.dirname(runtime)
    ensure_private_directory(parent)
    lock = os.path.join(parent, ".%s.runtime" % os.path.basename(runtime))
    with exclusive_file_lock(lock, private=True):
        if os.path.isfile(server):
            return runtime
        temporary = tempfile.mkdtemp(prefix=".%s." % os.path.basename(runtime), dir=parent)
        try:
            source = _source_root()
            for item in _RUNTIME_ITEMS:
                origin = os.path.join(source, item)
                destination = os.path.join(temporary, item)
                if os.path.isdir(origin):
                    shutil.copytree(origin, destination,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "golden", "build"))
                elif os.path.isfile(origin):
                    shutil.copy2(origin, destination)
            if not os.path.isfile(os.path.join(temporary, "scripts", "mcp_server.py")):
                raise RuntimeError("MCP runtime source is incomplete (scripts/mcp_server.py is missing)")
            os.replace(temporary, runtime)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    return runtime


def server_command(home=None, runtime_dir=None):
    """Return the command for the stable user-owned runtime, never this checkout."""
    runtime = runtime_dir or runtime_path(home=home)
    server = os.path.join(runtime, "scripts", "mcp_server.py")
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
    backup = config_file + ".bak." + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(config_file, backup)
    return backup


def _safe_args(args):
    """Redact secret-bearing option, header, and environment values for install records."""
    safe = []
    redact_next = False
    environment_next = False
    for argument in args:
        text = str(argument)
        if redact_next:
            safe.append("[REDACTED]")
            redact_next = False
        elif environment_next:
            name, separator, value = text.partition("=")
            safe.append(name + "=[REDACTED]" if separator and _SECRET_ARGUMENT.search(name) else text)
            environment_next = False
        elif text in _HEADER_OPTIONS:
            safe.append(text)
            redact_next = True
        elif text.startswith("--header="):
            safe.append("--header=[REDACTED]")
        elif text.startswith("-H") and len(text) > 2:
            safe.append("-H[REDACTED]")
        elif text in _ENVIRONMENT_OPTIONS:
            safe.append(text)
            environment_next = True
        elif text.startswith("--env="):
            name, separator, value = text[len("--env="):].partition("=")
            safe.append("--env=" + name + "=[REDACTED]"
                        if separator and _SECRET_ARGUMENT.search(name) else text)
        elif _SECRET_ARGUMENT.search(text.split(":", 1)[0]) and ":" in text:
            safe.append("[REDACTED]")
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


def _merge_target(target, command, args, do_backup):
    """Lock read/merge/backup/write as one operation for a single config file."""
    state = {"changed": False, "backup": None}

    def update(existing):
        if not isinstance(existing, dict):
            raise ValueError("configuration root must be a JSON object")
        replacement, changed = merge_entry(existing, command, args)
        if changed and do_backup:
            state["backup"] = _backup_config(target)
        state["changed"] = changed
        return replacement

    try:
        atomic_update_json(target, update, default={}, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"ok": False, "reason": "bad_json", "error": str(exc)}
    except ValueError as exc:
        return {"ok": False, "reason": "bad_json", "error": str(exc)}
    except OSError as exc:
        return {"ok": False, "reason": "write_failed", "error": str(exc)}
    return {"ok": True, **state}


def _recovery_state(changed_targets):
    return {
        target: {
            "status": "changed",
            "backup": backup,
            "action": "restore backup before retrying",
        }
        for target, backup in changed_targets
    }


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
        runtime = runtime_path(home=home)
        if not dry_run:
            try:
                runtime = _copy_runtime(runtime)
            except (OSError, RuntimeError) as exc:
                return _result(False, targets, False, [], reason="runtime_copy_failed", error=str(exc),
                               hint="Could not create the user-owned MCP runtime. Check disk permissions and retry.")
        command, args = server_command(runtime_dir=runtime)
    args = list(args or [])
    record_path = record_path or install_record_path(home=home)

    for target in targets:
        directory = os.path.dirname(target)
        if not os.path.isdir(directory) and not create_dir:
            return _result(False, [target], False, [], reason="no_config_dir",
                           hint="Claude Desktop configuration directory was not found. "
                                "Install Claude Desktop or pass mcp-install --config <file>.")
    if dry_run:
        prepared = []
        for target in targets:
            error, existing = _read_config(target)
            if error:
                return _result(False, [target], False, [], reason=error["reason"], error=error["error"])
            new_config, changed = merge_entry(existing, command, args)
            prepared.append((target, new_config, changed))
        previews = [json.dumps(config, ensure_ascii=False, indent=2) for _, config, _ in prepared]
        return _result(True, targets, any(changed for _, _, changed in prepared), [], dry_run=True,
                       preview=previews[0] if previews else "{}", previews=previews)

    backups = []
    changed_any = False
    changed_targets = []
    for target in targets:
        directory = os.path.dirname(target)
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        outcome = _merge_target(target, command, args, do_backup)
        if not outcome["ok"]:
            if len(targets) == 1 and outcome["reason"] == "write_failed":
                # Existing callers relied on an explicit single-file replacement failure raising.
                raise OSError(outcome["error"])
            return _result(False, targets, changed_any, backups, reason=outcome["reason"],
                           error=outcome["error"], recovery=_recovery_state(changed_targets),
                           hint="Some host configurations were updated. Restore the listed backups before retrying.")
        if outcome["changed"]:
            changed_any = True
            if outcome["backup"]:
                backups.append(outcome["backup"])
            changed_targets.append((target, outcome["backup"]))

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


def _doctor_failure(detail, recovery):
    return {"name": "mcp-install", "ok": False, "detail": detail, "recovery": recovery}


def check_install(record_path=None, home=None, timeout=_HANDSHAKE_TIMEOUT):
    """Validate the sanitized install record and perform a bounded stdio initialize handshake."""
    record_path = record_path or install_record_path(home=home)
    try:
        with open(record_path, encoding="utf-8") as handle:
            record = json.load(handle)
    except FileNotFoundError:
        return _doctor_failure("No MCP install record found", "Run scripts/board.py mcp-install first.")
    except (OSError, json.JSONDecodeError) as exc:
        return _doctor_failure("MCP install record cannot be read: %s" % exc,
                               "Run scripts/board.py mcp-install again to create a fresh record.")
    command, args, paths = record.get("command"), record.get("args"), record.get("paths")
    if (record.get("server_name") != NAME or not isinstance(command, str)
            or not isinstance(args, list) or not args or not all(isinstance(arg, str) for arg in args)
            or not isinstance(paths, list) or not all(isinstance(path, str) for path in paths)):
        return _doctor_failure("MCP install record is invalid or incomplete",
                               "Run scripts/board.py mcp-install again; do not edit the install record.")
    server = args[0]
    if "[REDACTED]" in command or any("[REDACTED]" in arg for arg in args):
        return _doctor_failure("MCP install record contains redacted launch arguments",
                               "Run mcp-install without secret-bearing server arguments, then retry doctor.")
    if not os.path.isabs(server) or not os.path.isfile(server):
        return _doctor_failure("MCP server path is missing: %s" % server,
                               "Run scripts/board.py mcp-install to recreate the stable runtime.")
    executable = command if os.path.isabs(command) else shutil.which(command)
    if not executable or not os.path.isfile(executable):
        return _doctor_failure("MCP command is not executable: %s" % command,
                               "Install Python 3.10+ or rerun mcp-install with a valid interpreter.")
    for path in paths:
        error, config = _read_config(path)
        entry = config.get("mcpServers", {}).get(NAME) if not error and isinstance(config, dict) else None
        if entry != {"command": command, "args": args}:
            return _doctor_failure("MCP host config no longer matches the install record: %s" % path,
                                   "Run scripts/board.py mcp-install to repair the host configuration.")
    request = {"jsonrpc": "2.0", "id": _HANDSHAKE_ID, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "consilium-doctor", "version": "1"}}}
    try:
        completed = subprocess.run([command, *args], input=json.dumps(request) + "\n", text=True,
                                   capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return _doctor_failure("MCP initialize handshake timed out after %ss" % timeout,
                               "Run scripts/board.py mcp-install, then completely restart Claude Desktop.")
    except OSError as exc:
        return _doctor_failure("MCP server could not start: %s" % exc,
                               "Check the Python command and rerun scripts/board.py mcp-install.")
    try:
        replies = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        replies = []
    valid = any(reply.get("id") == _HANDSHAKE_ID
                and reply.get("result", {}).get("serverInfo", {}).get("name") == NAME
                for reply in replies if isinstance(reply, dict))
    if completed.returncode != 0 or not valid:
        return _doctor_failure("MCP initialize handshake failed",
                               "Inspect the server error, rerun scripts/board.py mcp-install, then restart Claude Desktop.")
    return {"name": "mcp-install", "ok": True, "detail": "MCP runtime responds to initialize"}
