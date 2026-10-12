""".skillignore: Hermes Agent и ClawHub ставят скилл из корня и сканируют каждый файл.

SKILL.md лежит в корне, поэтому без .skillignore Hermes skills-guard проверял весь
репозиторий: тесты на защиту от атак (`/etc/passwd`, `__import__('os')`) давали
CRITICAL, и установка блокировалась даже с --force. Гейт держит два инварианта:
.skillignore закрывает всё, что не входит в RUNTIME install.py, а в том, что
остаётся, нет правил Hermes уровня HIGH и выше.
"""
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = Path(HERE).parent
sys.path.insert(0, str(REPO))

import install  # noqa: E402

IGNORE_FILE = REPO / ".skillignore"


def _patterns():
    return [l.strip() for l in IGNORE_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def _ignored(rel, patterns):
    """Упрощённая копия _load_skill_ignore из Hermes tools/skills_guard.py."""
    segs = rel.split("/")
    if segs[-1] == "SKILL.md":
        return False
    for pat in patterns:
        anchored, p = pat.startswith("/"), pat.strip("/")
        if pat.endswith("/"):
            if rel.startswith(p + "/") or (not anchored and ("/" + p + "/") in ("/" + rel)):
                return True
        elif fnmatch.fnmatch(rel, p) or (not anchored and (
                fnmatch.fnmatch(segs[-1], p) or rel.startswith(p + "/"))):
            return True
    return False


def _tracked():
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def _in_runtime(rel):
    return any(rel == item or rel.startswith(item + "/") for item in install.RUNTIME)


def _always_scanned(rel):
    """SKILL.md Hermes не исключает ни в какой папке: такие файлы сканируются всегда."""
    return rel.split("/")[-1] == "SKILL.md"


def test_skillignore_covers_everything_outside_runtime():
    patterns = _patterns()
    leaked = sorted({p.split("/")[0] for p in _tracked()
                     if p not in (".skillignore", ".clawhubignore")
                     and not _in_runtime(p) and not _always_scanned(p)
                     and not _ignored(p, patterns)})
    assert not leaked, "Hermes отсканирует и заблокирует: %s" % ", ".join(leaked)


# Правила Hermes skills-guard v10 уровня HIGH и выше, которые здесь уже срабатывали.
RULES = [
    (re.compile("[\u200b-\u200d\u2060\u2062-\u2064\ufeff\u202a-\u202e\u2066-\u2069]"),
     "невидимый символ литералом"),
    (re.compile(r"^[^#\n]*os\.environ\b(?!\s*\.get\s*\()"), "os.environ целиком"),
    (re.compile(r"rm\s+-rf\s+[~/]"), "rm -rf по пути"),
    (re.compile(r"(?:curl|wget)\s+[^|\s][^\n]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b"), "curl | sh"),
    (re.compile(r"echo\s+[^\n]*\|\s*(?:python|perl|ruby|node|(?:ba|z)?sh\b)"), "echo | интерпретатор"),
    (re.compile(r"/etc/passwd|/etc/shadow"), "/etc/passwd"),
]
TEXT = {".py", ".md", ".json", ".sh", ".txt", ".yaml", ".yml", ".toml"}


def test_shipped_files_have_no_high_install_scanner_findings():
    patterns = _patterns()
    hits = []
    for rel in _tracked():
        shipped = _always_scanned(rel) or (_in_runtime(rel) and not _ignored(rel, patterns))
        if not shipped or Path(rel).suffix not in TEXT:
            continue
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.split("\n"), 1):
            for rx, why in RULES:
                if rx.search(line):
                    hits.append("%s:%d %s" % (rel, n, why))
    assert not hits, "; ".join(hits[:15])
