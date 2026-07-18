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


def _served_instructions(monkeypatch, lang):
    # lang=None → снять переменную (режим auto/unset)
    if lang is None:
        monkeypatch.delenv("CONSILIUM_LANG", raising=False)
    else:
        monkeypatch.setenv("CONSILIUM_LANG", lang)
    resp = mcp_server._handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    return resp["result"]["instructions"]

def test_initialize_en_appends_english_directive(monkeypatch):  # G1
    served = _served_instructions(monkeypatch, "en")
    assert served.startswith(INSTRUCTIONS)          # базовый контур целиком на месте
    assert served.endswith(_response_language_directive("en"))
    assert "answer entirely in english" in served.lower()

def test_initialize_ru_appends_russian_directive(monkeypatch):  # G1
    served = _served_instructions(monkeypatch, "ru")
    assert served.endswith(_response_language_directive("ru"))
    assert "отвечай целиком по-русски" in served.lower()

def test_initialize_auto_appends_nothing(monkeypatch):  # G1
    served = _served_instructions(monkeypatch, None)
    assert served == INSTRUCTIONS                    # ровно базовый контур, без довеска
    served_junk = _served_instructions(monkeypatch, "xyz")
    assert served_junk == INSTRUCTIONS               # мусор → тоже базовый (G4 на уровне initialize)

def test_rules_0_and_5_survive_every_mode(monkeypatch):  # G2
    # Правила безопасности и верности присутствуют во всех режимах — форс-блок их не вытесняет.
    for lang in ("en", "ru", None):
        served = _served_instructions(monkeypatch, lang)
        assert "0. БЕЗОПАСНОСТЬ ВЫШЕ ВСЕГО" in served, f"Rule 0 пропал в режиме {lang}"
        assert "5. КОНТУР ВЕРНОСТИ" in served, f"Rule 5 пропал в режиме {lang}"


def test_both_force_blocks_bow_to_rule0():  # G3
    # Клауза подчинения обязана быть в ОБОИХ форс-блоках — иначе фиксация языка могла бы
    # позиционно (она последняя) перебить и безопасность (Rule 0), и ров дословности (Rule 5:
    # «ENTIRELY in English» не должно переводить дословную 🔵-цитату).
    en = _response_language_directive("en").lower()
    ru = _response_language_directive("ru").lower()
    assert "never overrides rule 0" in en, "EN-блок потерял клаузу подчинения Rule 0"
    assert "rule 5" in en, "EN-блок не защищает ров верности (Rule 5)"
    assert "не перекрывает правило 0" in ru, "RU-блок потерял клаузу подчинения Правилу 0"
    assert "правило 5" in ru, "RU-блок не защищает ров верности (Правило 5)"


def test_guard_not_asleep_force_blocks_are_nonempty_and_distinct():  # G5
    # Если кто-то опустошит блок, «фиксация» станет молчаливым no-op — гард это ловит.
    en = _response_language_directive("en")
    ru = _response_language_directive("ru")
    assert len(en.strip()) > 40 and len(ru.strip()) > 40, "форс-блок схлопнулся до пустого"
    assert en != ru, "EN и RU блоки совпали — один из них потерян"


def test_doctor_reports_language_mode(monkeypatch):
    import doctor
    monkeypatch.setenv("CONSILIUM_LANG", "en")
    c = doctor.check_response_language()
    assert c["name"] == "response-language"
    assert c["ok"] is True and c.get("advisory") is True   # диагностика, не блокирует здоровье
    assert "en" in c["detail"] and "CONSILIUM_LANG" in c["detail"]


def test_doctor_language_mode_defaults_to_auto(monkeypatch):
    import doctor
    monkeypatch.delenv("CONSILIUM_LANG", raising=False)
    assert "auto" in doctor.check_response_language()["detail"]
    monkeypatch.setenv("CONSILIUM_LANG", "xyz")             # мусор → auto (как в directive)
    assert "auto" in doctor.check_response_language()["detail"]
