"""P0-гард: .mcp.json обязан стартовать сервер в ОБОИХ контекстах Claude Code.

Как Claude Code (проверено на 2.1.301) раскрывает конфиг MCP-сервера:
  * плагин: сначала буквальная замена `${CLAUDE_PLUGIN_ROOT}` (ровно такая строка, без `:-`)
    на путь плагина, затем `${VAR}` / `${VAR:-default}` из окружения процесса Claude;
    корневой `.mcp.json` плагина грузится ВСЕГДА, а инлайн `mcpServers` из plugin.json
    мержится поверх него по имени сервера;
  * проект (репо открыт как проект): только `${VAR}` / `${VAR:-default}` из окружения,
    CLAUDE_PLUGIN_ROOT там не задан; stdio-сервер стартует с cwd = корень проекта.
Отсюда схема: `.mcp.json` → `${CLAUDE_PLUGIN_ROOT:-.}` (проект), plugin.json → инлайн
`${CLAUDE_PLUGIN_ROOT}` с тем же именем (плагин; `:-.` там дал бы `./scripts` от cwd ЧУЖОГО
проекта → CONNECTION_CLOSED).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "consilium-principis"
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?)\}")


def _load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _expand(s, env):
    """Эмуляция подстановки Claude Code: задано → значение, иначе дефолт, иначе как есть."""
    def sub(m):
        body = m.group(1)
        name, sep, default = body.partition(":-")
        if name in env:
            return env[name]
        return default if sep else m.group(0)
    return _VAR.sub(sub, s)


def _plugin_expand(s, plugin_root, env):
    # плагин: буквальный `${CLAUDE_PLUGIN_ROOT}` заменяется ДО env-подстановки
    return _expand(s.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root)), env)


def _resolve(arg, cwd):
    p = Path(arg)
    return p if p.is_absolute() else Path(cwd) / p


def _project_server():
    return _load(".mcp.json")["mcpServers"][NAME]


def _plugin_server():
    # эффективный конфиг плагина: .mcp.json, поверх — инлайн из plugin.json
    merged = dict(_load(".mcp.json")["mcpServers"])
    merged.update(_load(".claude-plugin/plugin.json").get("mcpServers") or {})
    return merged[NAME]


def test_project_context_without_plugin_root_resolves(tmp_path):
    # репо открыт как проект: CLAUDE_PLUGIN_ROOT не задан, cwd = корень репо
    args = [_expand(a, env={}) for a in _project_server()["args"]]
    assert "${" not in " ".join(args), f"неразвёрнутая переменная: {args}"
    script = _resolve(args[0], cwd=ROOT)
    assert script.is_file(), f"{script} не существует — сервер упадёт с CONNECTION_CLOSED"
    assert script.resolve() == (ROOT / "scripts" / "mcp_server.py").resolve()


def test_project_context_with_plugin_root_env_resolves():
    args = [_expand(a, env={"CLAUDE_PLUGIN_ROOT": str(ROOT)}) for a in _project_server()["args"]]
    script = _resolve(args[0], cwd="/")
    assert script.is_file()


def test_plugin_context_resolves_from_foreign_cwd(tmp_path):
    # плагин: cwd = чужой проект пользователя, CLAUDE_PLUGIN_ROOT в env процесса НЕ задан
    args = [_plugin_expand(a, ROOT, env={}) for a in _plugin_server()["args"]]
    assert "${" not in " ".join(args)
    script = _resolve(args[0], cwd=tmp_path)
    assert script.is_file(), f"{script}: в плагине путь обязан идти от CLAUDE_PLUGIN_ROOT"
    assert Path(args[0]).is_absolute()


def test_plugin_inline_override_uses_literal_plugin_root():
    srv = _load(".claude-plugin/plugin.json")["mcpServers"][NAME]
    assert srv["args"] == ["${CLAUDE_PLUGIN_ROOT}/scripts/mcp_server.py"], (
        "в плагине нужна ровно буквальная форма — `:-default` Claude Code там не подставляет"
    )
    # команда синхронна с .mcp.json (Windows-оверрайд CONSILIUM_PYTHON работает в обоих)
    assert srv["command"] == _project_server()["command"]


def test_command_defaults_to_python3():
    cmd = _expand(_project_server()["command"], env={})
    assert cmd == "python3"
    assert _expand(_project_server()["command"], env={"CONSILIUM_PYTHON": "py"}) == "py"
