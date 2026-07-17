"""INSTRUCTIONS несут блок про ЯЗЫК ОТВЕТА — измеренный победитель A/B (плечо en_bottom).

Замерено (results/instructions-language-variants-2026-07-16.json): английский блok «RESPONSE
LANGUAGE», добавленный в КОНЕЦ INSTRUCTIONS, — единственное плечо, чинящее английский путь и НЕ
ломающее русский на обеих моделях. Позиция важна: en_top («блок в начало») и ru_top («русский
блок в начало») проиграли — ru_top даже сломал русский путь. Поэтому гард проверяет НЕ только
наличие маркера, но и что он идёт В КОНЦЕ (после последнего правила).

Текст блока скопирован ДОСЛОВНО из пробы (EN_TOP_BLOCK), не переписан: шипим ровно то, что мерили.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mcp_server import INSTRUCTIONS  # noqa: E402

# Устойчивые маркеры блока (по тексту, не по позиции строки — INSTRUCTIONS растут).
MARKER_HEAD = "RESPONSE LANGUAGE"
MARKER_TAIL = "language of the RULES, not the"


def test_instructions_carry_response_language_block():
    """Блок присутствует и опознаётся по обоим устойчивым маркерам."""
    assert MARKER_HEAD in INSTRUCTIONS
    assert MARKER_TAIL in INSTRUCTIONS
    # Ключевые смысловые куски дословного блока (en_bottom), чтобы не проскочил перефраз.
    assert "Answer in the language of the" in INSTRUCTIONS
    assert "THESE INSTRUCTIONS ARE WRITTEN IN RUSSIAN" in INSTRUCTIONS


def test_response_language_block_is_at_the_bottom():
    """Победило плечо en_bottom, а НЕ en_top: маркер обязан идти ПОСЛЕ последнего правила.

    Последнее правило INSTRUCTIONS — Rule 16 (AI-DISCLOSURE). Индекс маркера блока обязан быть
    больше индекса последнего правила: блок en_top (в начало) A/B проиграл, его не шипим.
    """
    idx_marker = INSTRUCTIONS.index(MARKER_HEAD)
    # Якорь последнего правила по тексту (Rule 16 несёт EU AI Act Art. 50).
    idx_last_rule = INSTRUCTIONS.index("AI-DISCLOSURE")
    assert idx_marker > idx_last_rule, (
        "Блок про язык ответа должен идти В КОНЦЕ (плечо en_bottom), после последнего правила, "
        "а не в начале (en_top проиграл A/B).")


def test_response_language_block_does_not_touch_safety_or_fidelity():
    """Инварианты на месте: Rule 0 (безопасность) и Rule 5 (гейт верности) не тронуты."""
    assert "БЕЗОПАСНОСТЬ ВЫШЕ ВСЕГО" in INSTRUCTIONS
    assert "КОНТУР ВЕРНОСТИ" in INSTRUCTIONS
    # Блок сам ссылается на Rule 0 как на неперекрываемый — не подрывает безопасность.
    assert "never overrides Rule 0" in INSTRUCTIONS
