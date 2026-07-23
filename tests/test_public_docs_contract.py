"""Public documentation contracts: portable, honest, and locally reproducible."""
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DOCS = (
    "README.md",
    "README.ru.md",
    "QUICKSTART.en.md",
    "QUICKSTART.md",
    "CONNECT-MCP.en.md",
    "CONNECT-MCP.md",
    "docs/CONNECT-HOSTS.en.md",
    "docs/CONNECT-HOSTS.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "PRIVACY_POLICY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
    "GOVERNANCE.md",
)

LANGUAGE_PAIRS = (
    ("README.md", "README.ru.md"),
    ("QUICKSTART.en.md", "QUICKSTART.md"),
    ("CONNECT-MCP.en.md", "CONNECT-MCP.md"),
    ("docs/CONNECT-HOSTS.en.md", "docs/CONNECT-HOSTS.md"),
)

PAIR_COMMANDS = {
    ("README.md", "README.ru.md"): (
        "python3 install.py",
        "py install.py",
        "python3 scripts/board.py mcp-config --json",
    ),
    ("QUICKSTART.en.md", "QUICKSTART.md"): (
        "python3 install.py",
        "py install.py",
        "python3 scripts/board.py mcp-config --json",
        "py -3 scripts/board.py mcp-config --json",
    ),
    ("CONNECT-MCP.en.md", "CONNECT-MCP.md"): (
        "python3 ~/consilium-principis/scripts/board.py mcp-install",
        "py -3 ~/consilium-principis/scripts/board.py mcp-install",
        "python3 scripts/board.py mcp-config --json",
        "py -3 scripts/board.py mcp-config --json",
    ),
    ("docs/CONNECT-HOSTS.en.md", "docs/CONNECT-HOSTS.md"): (
        "python3 scripts/board.py mcp-config --json",
        "py -3 scripts/board.py mcp-config --json",
        "py -3 scripts/board.py mcp-install",
    ),
}

NUMERIC_TOOL_COUNT = re.compile(
    r"(?:\b\d+(?:[.,]\d+)?\s*[-–—]?\s*(?:MCP[\s-]*)?"
    r"(?:tools?|тул(?:ов|а|ы)?)\b|\b(?:MCP[\s-]*)?"
    r"(?:tools?|тул(?:ов|а|ы)?)\s*(?:count\s*)?"
    r"(?:(?::|\()|\bis\b|[-–—=])?\s*\d+\b|"
    r"\bколичество\s+(?:MCP[\s-]*)?тул(?:ов|а|ы)?\s*=\s*\d+\b)",
    re.I,
)


def public_docs_text():
    return "\n".join((ROOT / document).read_text(encoding="utf-8") for document in PUBLIC_DOCS)


def test_public_docs_do_not_claim_untested_windows_support():
    documents = public_docs_text()
    assert "works out of the box" not in documents.lower()
    assert "работает из коробки" not in documents.lower()


def test_connect_docs_do_not_hard_code_tool_count():
    assert not NUMERIC_TOOL_COUNT.search(public_docs_text())


@pytest.mark.parametrize(
    "expression",
    (
        "72 tools",
        "MCP tools: 72",
        "72 MCP-tool",
        "тулов: 72",
        "tools 72",
        "tools — 72",
        "MCP tool count is 72",
        "tools = 72",
        "количество MCP-тулов = 72",
    ),
)
def test_numeric_tool_count_pattern_rejects_count_first_and_label_first_forms(expression):
    assert NUMERIC_TOOL_COUNT.search(expression), expression


def test_public_markdown_links_resolve_locally():
    link = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
    missing = []
    for document in PUBLIC_DOCS:
        path = ROOT / document
        for target in link.findall(path.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0].strip("<>")
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            if not (path.parent / target).exists():
                missing.append(f"{document}: {target}")
    assert not missing, "broken local Markdown links:\n  " + "\n  ".join(missing)


def test_public_docs_do_not_expose_private_corpus_paths():
    assert not re.search(r"(?:^|[\\s`])/(?:Users|home)/[^\\s`]*(?:advisors|council)/", public_docs_text())


def test_connect_docs_prefer_reproducible_generated_config():
    for document in ("README.md", "README.ru.md", "QUICKSTART.md", "CONNECT-MCP.md", "docs/CONNECT-HOSTS.md"):
        assert "python3 scripts/board.py mcp-config --json" in (ROOT / document).read_text(encoding="utf-8")


def test_public_docs_do_not_describe_search_as_three_modes():
    assert not re.search(r"(?:three|три)\s+(?:search\s+)?(?:modes|режим[а-я]*)", public_docs_text(), re.I)


def test_connect_docs_do_not_claim_untested_cowork_bridge():
    connect_docs = "\n".join(
        (ROOT / document).read_text(encoding="utf-8")
        for document in ("CONNECT-MCP.md", "docs/CONNECT-HOSTS.md")
    )
    assert "бриджит их в песочницу Cowork" not in connect_docs
    assert "в Desktop, и в Cowork" not in connect_docs
    assert "один конфиг включает тулы" not in connect_docs


def test_host_matrix_makes_no_supported_claim_without_host_smoke():
    hosts = (ROOT / "docs/CONNECT-HOSTS.md").read_text(encoding="utf-8")

    assert "Claude Code и Claude Desktop проверены" not in hosts
    assert "✅ да" not in hosts
    assert "экспериментальн" in hosts


def test_windows_host_guide_describes_the_generated_interpreter_path():
    hosts = (ROOT / "docs/CONNECT-HOSTS.md").read_text(encoding="utf-8")

    assert "явного фикса/детекта нет" not in hosts
    assert re.search(r"точный путь к\s+запущенному интерпретатору", hosts)


def test_windows_mcp_guides_use_py_launcher_not_python3():
    hosts = (ROOT / "docs/CONNECT-HOSTS.md").read_text(encoding="utf-8")
    connect = (ROOT / "CONNECT-MCP.md").read_text(encoding="utf-8")
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    russian = (ROOT / "README.ru.md").read_text(encoding="utf-8")

    assert "py -3 scripts/board.py mcp-config --json" in hosts
    assert "py -3 scripts/board.py mcp-install" in hosts
    assert "py -3 ~/consilium-principis/scripts/board.py mcp-install" in connect
    assert "py -3 scripts/board.py mcp-config --json" in connect
    assert "py -3 scripts/board.py mcp-config --json" in english
    assert "py -3 scripts/board.py mcp-config --json" in russian


def test_en_ru_entry_points_keep_mechanical_facts_aligned():
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    russian = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    registry = (ROOT / "server.json").read_text(encoding="utf-8")

    en_version = re.search(r"early access \(v([^)]*)\)", english).group(1)
    ru_version = re.search(r"ранний доступ \(v([^)]*)\)", russian).group(1)
    release_version = re.search(r"releases/download/v([0-9][^/\"]*)/", registry).group(1)
    assert (en_version, ru_version, release_version) == (en_version,) * 3

    for command in ("python3 install.py", "py install.py", "python3 scripts/board.py mcp-config --json"):
        assert command in english
        assert command in russian

    assert "experimental" in english
    assert "эксперименталь" in russian
    tool_count = re.compile(r"\b\d+\s+(?:(?:MCP )?tools?|тул(?:ов|а|ы)?)\b", re.I)
    assert not tool_count.search(english)
    assert not tool_count.search(russian)


def test_document_language_pairs_keep_release_versions_and_links_aligned():
    registry = (ROOT / "server.json").read_text(encoding="utf-8")
    release_url = re.search(r'"identifier": "([^"]*releases/download/v[^\"]+)"', registry).group(1)
    release_version = re.search(r"releases/download/v([^/]+)/", release_url).group(1)

    for english_path, russian_path in LANGUAGE_PAIRS:
        english = (ROOT / english_path).read_text(encoding="utf-8")
        russian = (ROOT / russian_path).read_text(encoding="utf-8")
        assert f"v{release_version}" in english
        assert f"v{release_version}" in russian
        assert release_url in english
        assert release_url in russian


def test_document_language_pairs_link_to_each_other():
    link = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")

    def _references(text, target):
        # Версии-пары ссылаются друг на друга. Принимаем И относительную ссылку (`QUICKSTART.en.md`),
        # И абсолютный URL с тем же именем файла (`.../blob/master/QUICKSTART.en.md`): шипуемый
        # QUICKSTART.md обязан вести на не-шипуемую пару абсолютом, иначе в установленном скилле
        # ссылка мертва (см. test_shipped_md_relative_links_resolve_in_installed_tree).
        base = Path(target).name
        for t in link.findall(text):
            path = t.split("#", 1)[0].rstrip("/")
            if path == target or path.rsplit("/", 1)[-1] == base:
                return True
        return False

    for english_path, russian_path in LANGUAGE_PAIRS:
        english = (ROOT / english_path).read_text(encoding="utf-8")
        russian = (ROOT / russian_path).read_text(encoding="utf-8")
        english_target = str(Path(russian_path).relative_to(Path(english_path).parent))
        russian_target = str(Path(english_path).relative_to(Path(russian_path).parent))
        assert _references(english, english_target), f"{english_path} не ссылается на пару"
        assert _references(russian, russian_target), f"{russian_path} не ссылается на пару"


def test_document_language_pairs_keep_install_commands_aligned():
    for pair, commands in PAIR_COMMANDS.items():
        for document in pair:
            text = (ROOT / document).read_text(encoding="utf-8")
            for command in commands:
                assert command in text, f"{document} is missing {command!r}"


def test_host_status_matrix_keeps_the_same_hosts_and_warning_level_in_both_languages():
    normalized_names = {"Универсальный MCP-хост": "Universal MCP host"}

    def status_class(status):
        status = status.casefold()
        if "experimental" in status or "эксперимент" in status:
            return "experimental"
        if "unverified" in status or "не проверено" in status:
            return "unverified"
        if "host-dependent" in status or "зависит от хоста" in status:
            return "host-dependent"
        return status

    def matrix(path):
        in_host_table = False
        rows = []
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) != 6 or not (cells[0] == cells[-1] == ""):
                if in_host_table:
                    break
                continue
            if cells[1] in {"Host", "Хост"}:
                in_host_table = True
                continue
            if in_host_table and cells[1] != "---":
                rows.append((normalized_names.get(cells[1], cells[1]), status_class(cells[4])))
        return rows

    expected = [
        ("Claude Code", "experimental"),
        ("Claude Code", "experimental"),
        ("Claude Desktop", "experimental"),
        ("Cursor", "unverified"),
        ("Codex / OpenAI-style CLI", "unverified"),
        ("Gemini CLI", "unverified"),
        ("Universal MCP host", "host-dependent"),
    ]
    english = matrix("docs/CONNECT-HOSTS.en.md")
    russian = matrix("docs/CONNECT-HOSTS.md")
    assert set(english) == set(russian) == set(expected)
    assert [name for name, _ in english] == [name for name, _ in russian] == [name for name, _ in expected]
    assert english == russian == expected


def test_build_manual_check_is_reproducible():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_manual.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
