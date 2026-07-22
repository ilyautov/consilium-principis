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


def test_build_manual_check_is_reproducible():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_manual.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
