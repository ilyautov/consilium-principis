"""Public documentation contracts: portable, honest, and locally reproducible."""
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DOCS = (
    "README.md",
    "README.ru.md",
    "QUICKSTART.md",
    "CONNECT-MCP.md",
    "docs/CONNECT-HOSTS.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "PRIVACY_POLICY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
    "GOVERNANCE.md",
)


def public_docs_text():
    return "\n".join((ROOT / document).read_text(encoding="utf-8") for document in PUBLIC_DOCS)


def test_public_docs_do_not_claim_untested_windows_support():
    documents = public_docs_text()
    assert "works out of the box" not in documents.lower()
    assert "работает из коробки" not in documents.lower()


def test_connect_docs_do_not_hard_code_tool_count():
    assert not re.search(r"\b(?:60|61)\s+(?:(?:MCP )?tools?|тул(?:ов|а)?)\b", public_docs_text(), re.I)


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
    tool_count = re.compile(r"\b\d+\s+(?:(?:MCP )?tools?|тул(?:ов|а)?)\b", re.I)
    assert not tool_count.search(english)
    assert not tool_count.search(russian)


def test_build_manual_check_is_reproducible():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_manual.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
