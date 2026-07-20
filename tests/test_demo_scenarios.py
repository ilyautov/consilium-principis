"""Регресс-гард корпус-зависимых демо-сценариев: A (misattribution), C (crosslingual),
клэш (illustrative). Каждый несёт проверяемое ядро из живого гейта; тут стережём честность.

Корпуса gitignored → без build/corpus.jsonl тесты бежали бы только локально. В CI их
размораживает закоммиченная фикстура tests/fixtures/demo_corpora/<slug>.jsonl: conftest
материализует её в advisors/<slug>/build/corpus.jsonl (только если реальный не собран).
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, os.path.join(_ROOT, "scripts", "demo"))

import conftest

_HAVE_MARCUS = conftest.demo_corpus_available("marcus-aurelius")
_HAVE_BOTH = _HAVE_MARCUS and conftest.demo_corpus_available("machiavelli")

pytestmark = pytest.mark.usefixtures("demo_pd_corpora")

import misattribution_demo as mis
import crosslingual_demo as cross
import clash_demo as clash


def _assert_clean(lines):
    """Общий гард кадра: ноль путей/JSON и ноль длинного тире «—» (AI-маркер)."""
    for _style, text in lines:
        low = text.lower()
        assert ".json" not in low and ".jsonl" not in low and "advisors/" not in low
        assert "—" not in text


# ── A: цитата не в тех устах ──
@pytest.mark.skipif(not _HAVE_BOTH, reason="нет корпусов marcus+machiavelli ни живых, ни фикстуры")
def test_misattribution_catches_wrong_mouth():
    wrong, right, reason = mis.run()
    assert wrong["marker"] == "violation" and reason        # чужая атрибуция снята
    assert right["marker"] == "blue"                        # верная — держится


@pytest.mark.skipif(not _HAVE_BOTH, reason="нет корпусов marcus+machiavelli ни живых, ни фикстуры")
def test_misattribution_frame_clean_both_langs():
    for lang in ("ru", "en"):
        lines = mis.transcript(lang=lang)
        assert any("⛔" in t for _, t in lines) and any("✅" in t for _, t in lines)
        _assert_clean(lines)


# ── C: спросил по-русски, 🔵 по англ. тексту ──
@pytest.mark.skipif(not _HAVE_MARCUS, reason="нет корпуса marcus-aurelius ни живого, ни фикстуры")
def test_crosslingual_anchor_is_blue():
    fc = cross.run()
    assert fc["status"] == "🔵" and fc["verbatim"] is True


@pytest.mark.skipif(not _HAVE_MARCUS, reason="нет корпуса marcus-aurelius ни живого, ни фикстуры")
def test_crosslingual_frame_clean():
    _assert_clean(cross.transcript(lang="ru"))
    _assert_clean(cross.transcript(lang="en"))


# ── клэш (иллюстративный) ──
@pytest.mark.skipif(not _HAVE_MARCUS, reason="нет корпуса marcus-aurelius ни живого, ни фикстуры")
def test_clash_blue_core_verified_and_marked_illustrative():
    fc = clash.run()
    assert fc["status"] == "🔵"                             # проверяемое ядро реально
    for lang in ("ru", "en"):
        lines = clash.transcript(lang=lang)
        joined = " ".join(t for _, t in lines).lower()
        # честная пометка: доводы 🟡 не сверены, пример иллюстративен
        assert "🟡" in " ".join(t for _, t in lines)
        assert ("иллюстратив" in joined) or ("illustrative" in joined)
        _assert_clean(lines)
