#!/usr/bin/env python3
"""Подключить Consilium как локальный stdio-MCP в claude_desktop_config.json — СКРИПТОМ, не руками.

Зачем: ручная правка JSON — трение и шанс снести соседние серверы. Здесь идемпотентный МЕРДЖ
(сохраняет ollama-bridge/wildberries/ozon и пр.), с бэкапом. Правим ВНЕШНИЙ конфиг чужого
приложения → бэкап обязателен, dry-run по умолчанию доступен, рестарт Claude Desktop после.
Путь к серверу строится от __file__ (cwd при спавне не определён — см. CONNECT-MCP.md).

Чистые функции (тестируемы без касания реального конфига):
  • config_path(platform, home) — где живёт claude_desktop_config.json под ОС
  • merge_entry(cfg, command, args) — (новый_cfg, changed): мердж, сохраняя прочие серверы
  • install(...) — прочитать/смерджить/записать (с бэкапом); вернуть отчёт
"""
import os
import sys
import json
import time
import shutil

NAME = "consilium-principis"


def config_path(platform=None, home=None, appdata=None):
    platform = platform or sys.platform
    home = home or os.path.expanduser("~")
    if platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Claude",
                            "claude_desktop_config.json")
    if platform.startswith("win"):
        base = appdata or os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(base, "Claude", "claude_desktop_config.json")
    return os.path.join(home, ".config", "Claude", "claude_desktop_config.json")


def server_command():
    """(интерпретатор, [путь к mcp_server.py]) — абсолютно, от __file__."""
    server = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    return sys.executable, [server]


def merge_entry(cfg, command, args, name=NAME):
    """Вернуть (новый_cfg, changed). Сохраняет существующие mcpServers; идемпотентно."""
    cfg = dict(cfg or {})
    servers = dict(cfg.get("mcpServers") or {})
    entry = {"command": command, "args": list(args)}
    if servers.get(name) == entry:
        return cfg, False
    servers[name] = entry
    cfg["mcpServers"] = servers
    return cfg, True


def install(config_file=None, command=None, args=None, do_backup=True,
            create_dir=False, dry_run=False):
    config_file = config_file or config_path()
    if command is None:
        command, args = server_command()
    d = os.path.dirname(config_file)
    if not os.path.isdir(d) and not create_dir:
        return {"ok": False, "reason": "no_config_dir", "path": config_file,
                "hint": "Каталог Claude Desktop не найден — установлен ли он? "
                        "Или передай свой путь: mcp-install --config <файл>."}
    existing = {}
    if os.path.isfile(config_file):
        try:
            existing = json.load(open(config_file, encoding="utf-8"))
        except Exception as e:
            return {"ok": False, "reason": "bad_json", "path": config_file, "error": str(e)}
    new_cfg, changed = merge_entry(existing, command, args)
    if not changed:
        return {"ok": True, "changed": False, "path": config_file,
                "note": "уже подключён (идемпотентно)"}
    if dry_run:
        return {"ok": True, "changed": True, "dry_run": True, "path": config_file,
                "preview": json.dumps(new_cfg, ensure_ascii=False, indent=2)}
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    backup = None
    if do_backup and os.path.isfile(config_file):
        backup = config_file + ".bak." + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(config_file, backup)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(new_cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"ok": True, "changed": True, "path": config_file, "backup": backup,
            "restart": "Полностью выйди из Claude Desktop и открой заново."}
