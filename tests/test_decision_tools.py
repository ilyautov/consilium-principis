"""MCP-поверхность «Principis-расчёта» (Ф2, спека §7): тонкие обёртки ядра Ф1.

validate_decision_map / run_calculation / save_decision_map — никакой логики счёта
здесь нет (она в decision_map/mc_run, Ф1); тесты проверяют КОНТРАКТ тулов:
fail-closed отказы, RU-ошибки, «📐 рамку» (label_text), traversal-гард сохранения,
journal_line, интеграцию §4.3 (calculation-блок → строка Прогноз в outcome_nudge)
и правило «КАРТА РЕШЕНИЯ» в INSTRUCTIONS (few-shot формулы самосогласованы с
safe_expr). Ноль LLM, ноль сети.
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mcp_server import dispatch, list_tools


def _valid_map():
    """Валидная карта из спеки §1 (per-option форма модели, как в тестах Ф1)."""
    return {
        "question": "Куда вкладывать следующий месяц?",
        "options": [
            {"id": "ship_public", "name": "Выпустить публично",
             "description": "…", "reversibility": "one-way"},
            {"id": "status_quo", "name": "Ничего не делать",
             "description": "…", "reversibility": "two-way", "status_quo": True},
        ],
        "uncertainties": [
            {"id": "traction_prob", "kind": "event", "prob": 0.3,
             "confirmed_by_user": True, "elicited": "цитата ответа юзера"},
            {"id": "hours_to_ship", "kind": "continuous", "unit": "часы",
             "min": 20, "mode": 40, "max": 90,
             "confirmed_by_user": True, "elicited": "…"},
            {"id": "upside_hours", "kind": "continuous", "unit": "часы",
             "min": 50, "mode": 150, "max": 400,
             "confirmed_by_user": True, "elicited": "…"},
        ],
        "stakes": {"metric": "ценность в часах", "direction": "max"},
        "horizon": "3 месяца",
        "model": {
            "ship_public": {
                "expr": "traction_prob * upside_hours - hours_to_ship",
                "words": "вероятность трекшена умножить на выигрыш в часах, "
                         "минус часы на шиппинг",
            },
            "status_quo": {"expr": "0", "words": "ничего не делаем — ноль часов"},
        },
    }


def _has_cyrillic(s):
    return any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in s)


# ── validate_decision_map: тонкая обёртка гейтов честности ──────────────────

def test_decision_tools_registered():
    names = {t["name"] for t in list_tools()}
    assert "validate_decision_map" in names


def test_validate_tool_valid_map():
    r = dispatch("validate_decision_map", {"map": _valid_map()})
    assert r["valid"] is True and r["errors"] == []
    assert "run_calculation" in r["hint"]          # следующий шаг потока — прямо в ответе


def test_validate_tool_invalid_map_relays_council_questions():
    m = _valid_map()
    m["uncertainties"][0]["confirmed_by_user"] = False
    r = dispatch("validate_decision_map", {"map": m})
    assert r["valid"] is False and r["errors"]
    assert all(isinstance(e, str) and _has_cyrillic(e) for e in r["errors"])  # RU, не стектрейс
    # hint велит хосту доносить ошибки ВОПРОСАМИ совета, не техдампом
    assert "вопрос" in r["hint"].lower() and "техдамп" in r["hint"].lower()


def test_validate_tool_accumulates_all_errors():
    m = _valid_map()
    del m["stakes"]
    m["uncertainties"][1]["min"] = 999               # min > mode
    r = dispatch("validate_decision_map", {"map": m})
    assert len(r["errors"]) >= 2                     # все вопросы за один заход


def test_validate_tool_non_dict_map():
    r = dispatch("validate_decision_map", {"map": "не карта"})
    assert r["valid"] is False and r["errors"]
