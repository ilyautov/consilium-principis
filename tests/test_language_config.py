"""Гарды языкового выключателя CONSILIUM_LANG. Форс-блок фиксирует язык ответа поверх
автоподстройки en_bottom, НЕ ослабляя безопасность (клауза Правила 0). Спека:
docs/superpowers/specs/2026-07-18-language-config-design.md."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import mcp_server  # noqa: E402
from mcp_server import _response_language_directive, INSTRUCTIONS  # noqa: E402


def test_en_directive_forces_english_and_bows_to_rule0():
    d = _response_language_directive("en")
    assert d, "en → непустой форс-блок"
    low = d.lower()
    assert "english" in low
    assert "rule 0" in low  # клауза подчинения безопасности

def test_ru_directive_forces_russian_and_bows_to_rule0():
    d = _response_language_directive("ru")
    assert d, "ru → непустой форс-блок"
    assert "по-русски" in d.lower()
    assert "правило 0" in d.lower()  # клауза подчинения безопасности

def test_auto_and_empty_and_junk_yield_no_directive():
    # G4 fail-safe: всё, кроме en/ru, → пустая строка (базовый en_bottom, без мусора)
    for val in ("auto", "", "  ", "EN_GB", "xyz", "english", None):
        assert _response_language_directive(val) == "", f"{val!r} должно дать пустой блок"

def test_case_and_whitespace_insensitive():
    assert _response_language_directive("  EN ") == _response_language_directive("en")
    assert _response_language_directive("Ru") == _response_language_directive("ru")
