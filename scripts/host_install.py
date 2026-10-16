#!/usr/bin/env python3
"""host_install — подключить Consilium к Codex CLI и Kimi Code CLI (скилл + MCP-сервер).

Вызывается из install.py (`python3 install.py --host codex|kimi|all`). Тот же дисциплинарный
контракт, что у mcp_install.py (Claude Desktop): атомарная запись, бэкап перед правкой, откат
при сбое, отказ писать аргументы с секретами, идемпотентность (второй запуск ничего не меняет),
dry-run без побочных эффектов и doctor-проверка с реальным stdio `initialize`.

Куда смотрит MCP-сервер (обоснование выбора пути):
  mcp_install.py для Claude Desktop копирует отдельный рантайм в ~/.consilium/mcp-runtime/<hash>,
  потому что у Desktop НЕТ папки скилла. У Codex и Kimi она есть, и именно её install.py
  обновляет на месте, не трогая доску (advisors/, board_config.json, data/). Поэтому команда
  сервера = `<python> <папка скилла хоста>/scripts/mcp_server.py`:
    • скилл и MCP-тулы хоста видят ОДНУ доску (сервер берёт корень от своего __file__);
    • путь стабилен: это не чекаут репо (ровно так протух старый путь в ~/.codex/config.toml),
      а установочная папка, которую переустановка обновляет, а не переносит;
    • отдельный versioned-рантайм развёл бы доску скилла и доску MCP по разным каталогам.

Codex CLI (проверено на 0.161.0):
  • скиллы ищет в $CODEX_HOME/skills/<имя>/SKILL.md (CODEX_HOME по умолчанию ~/.codex);
  • MCP регистрируем ТОЛЬКО через `codex mcp add/get` — TOML руками не правим. Если бинаря codex
    нет, печатаем точную команду для пользователя;
  • `codex mcp add` поверх существующей записи переписывает config.toml целиком: теряются
    под-таблицы [mcp_servers.<имя>.*] (например tools.<тул>.approval_mode) и комментарии.
    Поэтому перед add делаем бэкап, вырезаем текст под-таблиц и после add дописываем его
    обратно атомарно; итог сверяем через `codex mcp get --json`, при расхождении откат из бэкапа.
    Комментарии codex не сохраняет — они остаются в бэкапе.

Kimi Code CLI (проверено на 2.0.0):
  • MCP читает из $KIMI_CODE_HOME/mcp.json (по умолчанию ~/.kimi-code/mcp.json) в формате
    Claude: {"mcpServers": {имя: {command, args}}} — пишем через mcp_install._merge_target
    (лок + бэкап + атомарная замена, соседние серверы не трогаем);
  • скиллы ищет в ~/.kimi-code/skills, ~/.agents/skills, ~/.claude/skills и ~/.codex/skills.
    Если скилл уже стоит в ~/.claude/skills/<имя>, второй копии не делаем: Kimi подхватит его,
    и у Claude Code с Kimi будет общая доска.

Все домашние каталоги передаются параметрами (home=, codex_home=, kimi_home=), а внешние
команды идут через один runner, поэтому тесты работают только в tmp_path.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import mcp_install
from file_atomic import atomic_write_text

NAME = mcp_install.NAME
HOSTS = ("claude", "codex", "kimi")
_CODEX_TIMEOUT = 60


# ── каталоги ────────────────────────────────────────────────────────────────
def _home(home=None):
    return home or os.path.expanduser("~")


def codex_home(home=None, env_value=None):
    """$CODEX_HOME, иначе <home>/.codex. env_value подменяет переменную в тестах."""
    value = env_value if env_value is not None else os.environ.get("CODEX_HOME")
    return os.path.expanduser(value) if value else os.path.join(_home(home), ".codex")


def kimi_home(home=None, env_value=None):
    """$KIMI_CODE_HOME, иначе <home>/.kimi-code."""
    value = env_value if env_value is not None else os.environ.get("KIMI_CODE_HOME")
    return os.path.expanduser(value) if value else os.path.join(_home(home), ".kimi-code")


def claude_skill_dir(home=None, name=NAME):
    return os.path.join(_home(home), ".claude", "skills", name)


def codex_skill_dir(codex_dir, name=NAME):
    return os.path.join(codex_dir, "skills", name)


def kimi_skill_dir(kimi_dir, name=NAME):
    return os.path.join(kimi_dir, "skills", name)


def kimi_mcp_path(kimi_dir):
    return os.path.join(kimi_dir, "mcp.json")


def _has_skill(skill_dir):
    return os.path.isfile(os.path.join(skill_dir, "SKILL.md"))


def server_command(skill_dir, python=None):
    """Команда MCP-сервера из папки скилла (см. обоснование в докстринге модуля)."""
    server = os.path.join(os.path.abspath(skill_dir), "scripts", "mcp_server.py")
    return python or sys.executable, [server]


def plan(hosts, name=NAME, home=None, codex_dir=None, kimi_dir=None, target=None):
    """Шаги установки по хостам: где скилл, копировать ли его, куда регистрировать MCP.

    Kimi переиспользует скилл Claude Code, если он уже стоит или ставится в этом же прогоне.
    target (--target) допустим только для одного хоста.
    """
    codex_dir = codex_dir or codex_home(home)
    kimi_dir = kimi_dir or kimi_home(home)
    steps = []
    for host in hosts:
        if host == "claude":
            steps.append({"host": "claude", "skill_dir": target or claude_skill_dir(home, name),
                          "copy": True, "mcp": None})
        elif host == "codex":
            steps.append({"host": "codex", "skill_dir": target or codex_skill_dir(codex_dir, name),
                          "copy": True, "mcp": "codex", "codex_home": codex_dir})
        elif host == "kimi":
            claude_dir = claude_skill_dir(home, name)
            if not target and ("claude" in hosts or _has_skill(claude_dir)):
                steps.append({"host": "kimi", "skill_dir": claude_dir, "copy": False,
                              "reuse": "claude", "mcp": "kimi", "kimi_home": kimi_dir})
            else:
                steps.append({"host": "kimi", "skill_dir": target or kimi_skill_dir(kimi_dir, name),
                              "copy": True, "mcp": "kimi", "kimi_home": kimi_dir})
        else:
            raise ValueError("неизвестный хост: %s" % host)
    return steps


# ── общее ────────────────────────────────────────────────────────────────────
def _refuse_secrets(command, args):
    """Аргументы с секретами в конфиг хоста не пишем вовсе (тот же детектор, что у mcp_install)."""
    return mcp_install._safe_args([command, *args]) != [command, *args]


def _backup(path):
    if not os.path.isfile(path):
        return None
    backup = path + ".bak." + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(path, backup)
    return backup


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _check_failure(host, detail, recovery):
    return {"name": "%s-mcp" % host, "ok": False, "detail": detail, "recovery": recovery}


def _check_entry(host, command, args, timeout, rerun):
    """Путь сервера существует, интерпретатор исполним, stdio initialize проходит."""
    if not isinstance(command, str) or not isinstance(args, list) or not args:
        return _check_failure(host, "запись MCP неполная (нет command/args)", rerun)
    server = args[0]
    if not os.path.isabs(server) or not os.path.isfile(server):
        return _check_failure(host, "путь MCP-сервера не существует: %s" % server, rerun)
    executable = command if os.path.isabs(command) else shutil.which(command)
    if not executable or not os.path.isfile(executable):
        return _check_failure(host, "команда MCP не исполняется: %s" % command, rerun)
    status = mcp_install.initialize_handshake(command, args, timeout=timeout)
    if status != "ok":
        return _check_failure(host, "MCP initialize не прошёл (%s)" % status, rerun)
    return {"name": "%s-mcp" % host, "ok": True, "detail": "MCP-сервер отвечает на initialize: %s" % server}


# ── Codex ────────────────────────────────────────────────────────────────────
def _default_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=_CODEX_TIMEOUT, check=False)


def codex_command_line(command, args, name=NAME):
    """Точная команда для ручной регистрации (когда бинаря codex нет)."""
    return " ".join(shlex.quote(part) for part in ["codex", "mcp", "add", name, "--", command, *args])


def _codex_get(codex, runner, name=NAME):
    """Текущая запись из `codex mcp get --json` → (entry|None, error|None)."""
    completed = runner([codex, "mcp", "get", name, "--json"])
    if completed.returncode != 0:
        return None, None                                  # записи нет — это не ошибка
    try:
        data = json.loads(completed.stdout)
        transport = data.get("transport") or {}
        return {"command": transport.get("command"), "args": list(transport.get("args") or []),
                "type": transport.get("type")}, None
    except (ValueError, AttributeError, TypeError) as exc:
        return None, "codex mcp get вернул не-JSON: %s" % exc


_HEADER = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(?:#.*)?$")


def _table_name(line):
    match = _HEADER.match(line)
    return match.group(1) if match else None


def _is_server_table(header, name, sub=False):
    quoted = 'mcp_servers."%s"' % name
    plain = "mcp_servers.%s" % name
    for prefix in (plain, quoted):
        if sub and header.startswith(prefix + "."):
            return True
        if not sub and header == prefix:
            return True
    return False


def extract_server_subtables(toml_text, name=NAME):
    """Текст под-таблиц [mcp_servers.<name>.*] (tools.<тул>.approval_mode и т.п.).

    `codex mcp add` их выбрасывает — сохраняем дословно, чтобы дописать обратно.
    """
    blocks, current = [], None
    for line in (toml_text or "").splitlines():
        header = _table_name(line)
        if header is not None or line.lstrip().startswith("[["):
            if current:
                blocks.append(current)
            current = [line] if header is not None and _is_server_table(header, name, sub=True) else None
            continue
        if current is not None:
            current.append(line)
    if current:
        blocks.append(current)
    cleaned = []
    for block in blocks:
        while block and not block[-1].strip():
            block.pop()
        cleaned.append("\n".join(block))
    return "\n\n".join(cleaned)


def install_codex(skill_dir, codex_dir=None, home=None, runner=None, which=None,
                  dry_run=False, python=None, name=NAME):
    """Зарегистрировать MCP-сервер в Codex CLI через `codex mcp add`.

    Протухший путь (файл сервера исчез) или другая команда → замена. Совпадает → без изменений.
    """
    resolved = codex_home(home)
    codex_dir = codex_dir or resolved
    if runner is None and os.path.abspath(codex_dir) != os.path.abspath(resolved):
        # codex CLI правит $CODEX_HOME из окружения; чужой каталог мы бы молча не тронули.
        return {"ok": False, "host": "codex", "reason": "codex_home_mismatch",
                "hint": "Задай CODEX_HOME=%s в окружении и запусти снова." % codex_dir}
    runner = runner or _default_runner
    command, args = server_command(skill_dir, python=python)
    line = codex_command_line(command, args, name)
    base = {"host": "codex", "command": command, "args": args, "command_line": line,
            "config": os.path.join(codex_dir, "config.toml")}
    if _refuse_secrets(command, args):
        return {**base, "ok": False, "reason": "secret_args",
                "hint": "Аргументы похожи на секрет — в конфиг хоста не пишу."}
    codex = (which or shutil.which)("codex")
    if not codex:
        return {**base, "ok": False, "reason": "codex_not_found", "manual": True,
                "hint": "codex не найден в PATH. Выполни вручную: " + line}
    current, error = _codex_get(codex, runner, name)
    if error:
        return {**base, "ok": False, "reason": "codex_get_failed", "error": error}
    desired = {"command": command, "args": args}
    if current and current.get("command") == command and current.get("args") == args:
        return {**base, "ok": True, "changed": False, "action": "unchanged"}
    stale = bool(current) and not (current.get("args") and os.path.isfile(current["args"][0]))
    action = "add" if not current else ("replace_stale" if stale else "replace")
    if dry_run:
        return {**base, "ok": True, "changed": True, "dry_run": True, "action": action,
                "previous": current}

    config = base["config"]
    before = _read_text(config)
    preserved = extract_server_subtables(before, name) if current else ""
    backup = _backup(config)

    def rollback(reason, **extra):
        if backup:
            with open(backup, encoding="utf-8") as handle:
                atomic_write_text(config, handle.read())
        elif before is None and os.path.isfile(config):
            os.remove(config)                          # файла не было до нас — убираем то, что создал add
        return {**base, "ok": False, "reason": reason, "backup": backup,
                "rolled_back": bool(backup) or before is None, **extra}

    completed = runner([codex, "mcp", "add", name, "--", command, *args])
    if completed.returncode != 0:
        return rollback("codex_add_failed", error=(completed.stderr or completed.stdout or "").strip())
    if preserved:
        after = _read_text(config) or ""
        if preserved not in after:
            atomic_write_text(config, after.rstrip("\n") + "\n\n" + preserved + "\n")
    check, error = _codex_get(codex, runner, name)
    if error or not check or {"command": check.get("command"), "args": check.get("args")} != desired:
        return rollback("codex_verify_failed", error=error or "запись после add не совпала")
    return {**base, "ok": True, "changed": True, "action": action, "backup": backup,
            "previous": current, "preserved_subtables": bool(preserved)}


def check_codex(codex_dir=None, home=None, runner=None, which=None, timeout=mcp_install._HANDSHAKE_TIMEOUT,
                name=NAME):
    """Doctor для Codex: запись есть, путь жив, stdio initialize проходит."""
    rerun = "Запусти `python3 install.py --host codex`."
    codex = (which or shutil.which)("codex")
    if not codex:
        return _check_failure("codex", "codex не найден в PATH", "Поставь Codex CLI, затем " + rerun)
    resolved = codex_home(home)
    if runner is None and codex_dir and os.path.abspath(codex_dir) != os.path.abspath(resolved):
        return _check_failure("codex", "CODEX_HOME окружения не совпадает с %s" % codex_dir, rerun)
    current, error = _codex_get(codex, runner or _default_runner, name)
    if error:
        return _check_failure("codex", error, rerun)
    if not current:
        return _check_failure("codex", "в Codex нет MCP-сервера %s" % name, rerun)
    return _check_entry("codex", current.get("command"), current.get("args"), timeout, rerun)


# ── Kimi ─────────────────────────────────────────────────────────────────────
def install_kimi(skill_dir, kimi_dir=None, home=None, dry_run=False, python=None, create_dir=False):
    """Записать MCP-сервер в $KIMI_CODE_HOME/mcp.json (лок + бэкап + атомарно, соседей не трогаем)."""
    kimi_dir = kimi_dir or kimi_home(home)
    target = kimi_mcp_path(kimi_dir)
    command, args = server_command(skill_dir, python=python)
    base = {"host": "kimi", "command": command, "args": args, "config": target}
    if _refuse_secrets(command, args):
        return {**base, "ok": False, "reason": "secret_args",
                "hint": "Аргументы похожи на секрет — в конфиг хоста не пишу."}
    if not os.path.isdir(kimi_dir) and not create_dir:
        return {**base, "ok": False, "reason": "no_kimi_home",
                "hint": "Каталог %s не найден: поставь Kimi Code CLI или задай KIMI_CODE_HOME." % kimi_dir}
    error, existing = mcp_install._read_config(target)
    if error:
        return {**base, "ok": False, "reason": "bad_json", "error": error["error"]}
    if not isinstance(existing, dict):
        return {**base, "ok": False, "reason": "bad_json", "error": "корень mcp.json не объект"}
    previous = (existing.get("mcpServers") or {}).get(NAME)
    _, changed = mcp_install.merge_entry(existing, command, args)
    if not changed:
        return {**base, "ok": True, "changed": False, "action": "unchanged"}
    action = "add" if not previous else "replace"
    if dry_run:
        return {**base, "ok": True, "changed": True, "dry_run": True, "action": action,
                "previous": previous}
    os.makedirs(kimi_dir, exist_ok=True)
    outcome = mcp_install._merge_target(target, command, args, do_backup=True)
    if not outcome["ok"]:
        return {**base, "ok": False, "reason": outcome["reason"], "error": outcome.get("error")}
    return {**base, "ok": True, "changed": outcome["changed"], "action": action,
            "backup": outcome["backup"], "previous": previous}


def check_kimi(kimi_dir=None, home=None, timeout=mcp_install._HANDSHAKE_TIMEOUT):
    """Doctor для Kimi: запись в mcp.json есть, путь жив, stdio initialize проходит."""
    rerun = "Запусти `python3 install.py --host kimi`."
    target = kimi_mcp_path(kimi_dir or kimi_home(home))
    error, config = mcp_install._read_config(target)
    if error:
        return _check_failure("kimi", "mcp.json не читается: %s" % error["error"], rerun)
    entry = (config.get("mcpServers") or {}).get(NAME) if isinstance(config, dict) else None
    if not isinstance(entry, dict):
        return _check_failure("kimi", "в %s нет MCP-сервера %s" % (target, NAME), rerun)
    return _check_entry("kimi", entry.get("command"), entry.get("args"), timeout, rerun)
