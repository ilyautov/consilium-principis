import json
import re
from pathlib import Path

try:
    import tomllib  # stdlib только с Python 3.11+
except ModuleNotFoundError:  # 3.10 (заявленный минимум) — фолбэк на regex ниже
    tomllib = None

ROOT = Path(__file__).resolve().parent.parent


def _load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)["project"]["version"]
    # Python 3.10 без tomllib: вытащить version из таблицы [project] точечно.
    proj = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
    assert proj, "[project] не найден в pyproject.toml"
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', proj.group(1))
    assert m, "version не найден в таблице [project]"
    return m.group(1)


def _serverinfo_version():
    src = (ROOT / "scripts" / "mcp_server.py").read_text(encoding="utf-8")
    m = re.search(r'"serverInfo"\s*:\s*\{[^}]*"version"\s*:\s*"([^"]+)"', src)
    assert m, "serverInfo version не найден в mcp_server.py"
    return m.group(1)


def test_plugin_manifest_valid():
    p = _load_json(".claude-plugin/plugin.json")
    assert p["name"] == "consilium-principis"
    assert re.fullmatch(r"[a-z0-9-]+", p["name"]), "name должен быть kebab-case"
    assert p["description"].strip()
    assert "version" in p


def test_marketplace_manifest_valid():
    m = _load_json(".claude-plugin/marketplace.json")
    assert re.fullmatch(r"[a-z0-9-]+", m["name"]), "marketplace name kebab-case"
    assert m["owner"]["name"].strip()
    plugins = m["plugins"]
    assert len(plugins) == 1
    entry = plugins[0]
    assert entry["name"] == "consilium-principis"
    assert entry["source"] == {"source": "github", "repo": "ilyautov/consilium-principis"}
    assert "version" not in entry, "version только в plugin.json, не в marketplace.json"


def test_versions_in_sync():
    p = _load_json(".claude-plugin/plugin.json")
    mcpb = _load_json("manifest.json")
    reg = _load_json("server.json")
    assert (
        p["version"]
        == _pyproject_version()
        == _serverinfo_version()
        == mcpb["version"]
        == reg["version"]
    ), "версия рассинхронизирована между plugin.json/pyproject/serverInfo/manifest.json/server.json"


def test_mcpb_manifest_valid():
    # mcpb-манифест бандла (формат Anthropic, формерли DXT) — источник для `mcpb pack`.
    m = _load_json("manifest.json")
    assert m["manifest_version"] == "0.3", "текущая mcpb-схема — 0.3"
    assert m["name"] == "consilium-principis"
    srv = m["server"]
    assert srv["type"] == "python", "сервер запускается как python-бандл"
    assert srv["entry_point"] == "scripts/mcp_server.py"
    cfg = srv["mcp_config"]
    assert cfg["command"] == "python3"
    joined = " ".join(cfg["args"])
    assert "${__dirname}" in joined, "путь к энтрипоинту через переменную бандла, не абсолют"
    assert "mcp_server.py" in joined
    assert "/Users/" not in joined and "/opt/" not in joined, "ноль абсолютных путей"


def test_registry_server_json_valid():
    # server.json — манифест MCP Registry (registry.modelcontextprotocol.io).
    reg = _load_json("server.json")
    assert reg["name"] == "io.github.ilyautov/consilium-principis"
    assert re.fullmatch(
        r"io\.github\.[a-z0-9-]+/[a-z0-9-]+", reg["name"]
    ), "namespace должен быть io.github.<user>/<server> (GitHub-OAuth пруф)"
    assert reg["repository"]["source"] == "github"
    pkgs = reg["packages"]
    assert len(pkgs) == 1
    pkg = pkgs[0]
    assert pkg["registryType"] == "mcpb", "выбран формат mcpb (self-contained бандл)"
    ident = pkg["identifier"]
    # пруф владения mcpb: URL артефакта обязан содержать «mcp» (расширение .mcpb даёт это).
    assert ".mcpb" in ident and "mcp" in ident, "URL mcpb-артефакта обязан содержать 'mcp'"
    assert ident.startswith("https://github.com/ilyautov/consilium-principis/releases/")
    assert pkg["transport"]["type"] == "stdio"


def test_registry_sha256_is_flagged_placeholder_not_published():
    # fileSha256 намеренно сентинел, а не 64-нулевой фейк: publish с плейсхолдером
    # споткнётся громко. Гард ловит, если placeholder случайно уедет как «настоящий».
    reg = _load_json("server.json")
    sha = reg["packages"][0]["fileSha256"]
    is_real = bool(re.fullmatch(r"[0-9a-f]{64}", sha))
    is_sentinel = "REPLACE" in sha
    assert is_real or is_sentinel, "fileSha256 должен быть либо реальным 64-hex, либо явным сентинелом"


def test_mcp_json_uses_plugin_root_no_absolutes():
    raw = (ROOT / ".mcp.json").read_text(encoding="utf-8")
    m = json.loads(raw)
    srv = m["mcpServers"]["consilium-principis"]
    joined = " ".join(srv["args"])
    assert "${CLAUDE_PLUGIN_ROOT}" in joined
    assert "mcp_server.py" in joined
    assert "/Users/" not in raw and "/opt/" not in raw, "ноль абсолютных unix-путей"
    assert not re.search(r"[A-Za-z]:\\\\", raw), "ноль абсолютных windows-путей"


def test_thin_skill_exists_no_bash_scripts():
    sk = ROOT / "skills" / "consilium-principis" / "SKILL.md"
    assert sk.exists(), "тонкий skill плагина должен существовать"
    text = sk.read_text(encoding="utf-8")
    assert text.strip()
    assert text.startswith("---"), "нужен YAML-frontmatter с description"
    # тонкий skill драйвит через MCP-тулы, НЕ через bash-вызовы scripts/ (границу фиксируем)
    assert "scripts/" not in text, "skill не должен звать локальные scripts/ — только MCP-тулы"


def test_mcpb_manifest_windows_uses_py_launcher():
    # Windows: python.org НЕ создаёт python3.exe (только python.exe + py.exe), а python3.exe в
    # WindowsApps — Store-заглушка (App Execution Alias), которая молча открывает магазин вместо
    # запуска сервера. Поэтому mcpb-бандл на win32 стартует через Python Launcher `py -3`, а не
    # через `python3`. darwin/linux остаются на python3 (top-level command).
    m = _load_json("manifest.json")
    cfg = m["server"]["mcp_config"]
    assert cfg["command"] == "python3", "top-level (darwin/linux) остаётся python3"
    win = cfg["platform_overrides"]["win32"]
    assert win["command"] == "py", "на Windows запускаем через Python Launcher py.exe, не python3"
    assert "-3" in win["args"], "py -3 фиксирует ветку Python 3"
    joined = " ".join(win["args"])
    assert "${__dirname}" in joined and "mcp_server.py" in joined
    assert "/Users/" not in joined and "/opt/" not in joined, "ноль абсолютных путей в win32-оверрайде"


def test_mcp_json_command_windows_overridable():
    # Claude Code .mcp.json не умеет per-OS команду, но умеет подстановку ${VAR:-default} в поле
    # command. Дефолт остаётся python3 (mac/linux без изменений — ноль регресса), но перекрывается
    # CONSILIUM_PYTHON=py на Windows, где python3 обычно не резолвится.
    m = _load_json(".mcp.json")
    cmd = m["mcpServers"]["consilium-principis"]["command"]
    assert cmd == "${CONSILIUM_PYTHON:-python3}", (
        "команда плагина должна перекрываться CONSILIUM_PYTHON и падать в python3 по умолчанию"
    )


def test_example_mcp_json_neutral_no_machine_path():
    # Реальный mcp.json — личный, в .gitignore (машинный абсолют не течёт в git). В репо трекается
    # ТОЛЬКО mcp.example.json — гардим, что в НЁМ нет ничьего локального пути (нейтральный плейсхолдер).
    raw = (ROOT / "mcp.example.json").read_text(encoding="utf-8")
    assert "/Users/" not in raw, "ничей локальный путь в трекаемом mcp.example.json"
    assert "/opt/" not in raw
    m = json.loads(raw)  # валидный JSON
    assert "consilium-principis" in m["mcpServers"]
