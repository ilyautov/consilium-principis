import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _pyproject_version():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


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
    assert p["version"] == _pyproject_version() == _serverinfo_version()


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
