"""Регресс-гард честности демо-ассета (scripts/demo/refusal_demo.py).

Демо шипит GIF «докажет цитату или промолчит». Тесты стерегут, чтобы вердикты в кадре
шли из ЖИВОГО гейта верности, а не из хардкода: выдуманная цитата ОБЯЗАНА отвергаться,
реальная — давать 🔵 дословно. Плюс кадр чист от техношума (ни путей, ни JSON, ни тир-кодов).

Корпус советника gitignored (собирается локально) → без build/corpus.jsonl тесты
ПРОПУСКАЮТСЯ (как прочие корпус-зависимые тесты), CI остаётся зелёным офлайн.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, os.path.join(_ROOT, "scripts", "demo"))

_CORPUS = os.path.join(_ROOT, "advisors", "marcus-aurelius", "build", "corpus.jsonl")
pytestmark = pytest.mark.skipif(
    not os.path.isfile(_CORPUS),
    reason="корпус marcus-aurelius не собран (gitignored) — демо-гард пропущен")

import refusal_demo as demo


def test_fabricated_quote_is_refused():
    """Выдуманную «цитату Аврелия» гейт не подтверждает дословно и не даёт ей 🔵."""
    _real, fake = demo.verdicts()
    assert fake["verbatim"] is False
    assert fake["status"] != "🔵"


def test_real_line_is_blue_verbatim_with_source():
    """Реальная строка «Размышлений» проходит как 🔵 дословно и со своим источником."""
    real, _fake = demo.verdicts()
    assert real["status"] == "🔵"
    assert real["verbatim"] is True
    assert "meditations" in (real["source"] or "").lower()


def test_transcript_has_refusal_and_proof_beats():
    """В кадре обязаны быть и честный отказ (⛔), и дословный пруф (🔵) — оба дифференциатора."""
    lines = demo.transcript()
    styles = {s for s, _ in lines}
    assert "refuse" in styles and "proof" in styles
    assert any("⛔" in t for _, t in lines)
    assert any("🔵" in t for _, t in lines)


def test_prompt_suppressed_for_recorder():
    """--no-prompt (когда команду печатает VHS) убирает собственный промпт скрипта."""
    assert transcript_first_style(demo.transcript(include_prompt=True)) == "prompt"
    assert transcript_first_style(demo.transcript(include_prompt=False)) != "prompt"


def test_no_technical_noise_in_frame():
    """Rule 1/10: никаких путей/JSON/тир-кодов в кадре — только человекочитаемое."""
    for _style, text in demo.transcript():
        low = text.lower()
        assert ".jsonl" not in low and ".json" not in low and ".txt" not in low
        assert "advisors/" not in low and "build/" not in low
        assert "p1" not in low and "s1" not in low  # внутренние тир-коды не показываем


def transcript_first_style(lines):
    return lines[0][0] if lines else None
