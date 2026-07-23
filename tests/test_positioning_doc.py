"""Гард docs-сплита: внутренняя записка позиционирования (конкурентная стратегия) НЕ трекается в
публичном репо. Раньше гард требовал её НАЛИЧИЯ в docs/dev/; после сплита 2026-07-23 (внешний ревью:
стратегия/moat-анализ/GTM не должны ехать в public) инвариант перевёрнут — она живёт локально и
gitignored, а тест стережёт, чтобы она не вернулась в трекинг."""
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
REL = "docs/dev/positioning-vs-competitors.md"


def test_positioning_doc_stays_out_of_public_repo():
    try:
        r = subprocess.run(["git", "ls-files", REL], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
    except Exception:
        pytest.skip("git недоступен")
    if r.returncode != 0:
        pytest.skip("не git-воркри")
    assert not r.stdout.strip(), (
        f"{REL} снова трекается — внутренняя позиционная стратегия утекает в public-репо "
        f"(должна быть gitignored, см. docs-сплит)"
    )
