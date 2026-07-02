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


# ── run_calculation: валидация → МК-ядро + «📐 рамка» ───────────────────────

def test_run_calculation_registered():
    assert "run_calculation" in {t["name"] for t in list_tools()}


def test_run_calculation_returns_core_result_with_frame():
    r = dispatch("run_calculation", {"map": _valid_map(), "seed": 7, "n": 400})
    assert set(r["p_best"]) == {"ship_public", "status_quo"}
    assert "options" in r and "tornado" in r and "top_uncertainties" in r
    lt = r["label_text"]                             # готовая «📐 рамка» одной строкой
    assert lt.startswith("📐") and "3 величин" in lt
    assert "подтверждены тобой" in lt and "сид 7" in lt and "400 сценариев" in lt
    assert "не истина" in lt.lower()


def test_run_calculation_note_is_point_of_use_directive():
    r = dispatch("run_calculation", {"map": _valid_map(), "seed": 1, "n": 200})
    note = r["note"]
    assert "label_text" in note                      # показывать ТОЛЬКО с рамкой
    assert "2×2" in note                             # top_uncertainties → оси 2×2 (Ф3 — назвать)
    assert "save_decision_map" in note               # финал — предложить сохранить карту
    assert "🔵" in note and "📐" in note              # лейблы рядом, не смешивать


def test_run_calculation_deterministic_same_seed():
    a = dispatch("run_calculation", {"map": _valid_map(), "seed": 11, "n": 300})
    b = dispatch("run_calculation", {"map": _valid_map(), "seed": 11, "n": 300})
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_run_calculation_default_seed_is_fixed():
    # без seed → фикс-дефолт (повторный вызов воспроизводим байт-в-байт)
    a = dispatch("run_calculation", {"map": _valid_map(), "n": 200})
    b = dispatch("run_calculation", {"map": _valid_map(), "n": 200})
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert "сид" in a["label_text"]


def test_run_calculation_refuses_invalid_map_fail_closed():
    m = _valid_map()
    del m["stakes"]
    r = dispatch("run_calculation", {"map": m, "n": 100})
    assert "error" in r and r["errors"]              # отказ с гейт-ошибками
    assert all(_has_cyrillic(e) for e in r["errors"])
    assert "hint" in r and "вопрос" in r["hint"].lower()
    assert "p_best" not in r and "label_text" not in r   # никаких частичных чисел


def test_run_calculation_unconfirmed_number_refused():
    m = _valid_map()
    m["uncertainties"][2].pop("confirmed_by_user")
    r = dispatch("run_calculation", {"map": m, "n": 100})
    assert "error" in r and any("upside_hours" in e for e in r["errors"])


def test_run_calculation_bad_seed_fails_ru():
    r = dispatch("run_calculation", {"map": _valid_map(), "seed": "семь"})
    assert "error" in r and "сид" in r["error"].lower()


def test_run_calculation_bad_n_fails_ru():
    r = dispatch("run_calculation", {"map": _valid_map(), "n": 0})
    assert "error" in r and _has_cyrillic(r["error"])


# ── save_decision_map: артефакт карты (traversal-гард) + journal_line ───────

@pytest.fixture
def board_root(tmp_path, monkeypatch):
    """Корень доски → tmp (write-гард и артефакты не трогают репо)."""
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    return tmp_path


def test_save_decision_map_registered():
    assert "save_decision_map" in {t["name"] for t in list_tools()}


def test_save_decision_map_writes_artifact(board_root):
    r = dispatch("save_decision_map",
                 {"map": _valid_map(), "slug": "ship-or-wait", "n": 200})
    assert r["ok"] is True
    assert re.fullmatch(r"decisions/\d{4}-\d{2}-\d{2}-ship-or-wait\.json", r["path"])
    doc = json.loads((board_root / r["path"]).read_text(encoding="utf-8"))
    assert doc["map"]["question"] == _valid_map()["question"]     # карта в файле целиком
    # МК-сводка (predicted) — в самом файле: при резолюции сравнивается с фактом (§6)
    assert doc["calculation"]["predicted"]
    assert doc["calculation"]["result"]["p_best"]
    assert doc["calculation"]["seed"] == 2026 and doc["calculation"]["n"] == 200


def test_save_returns_journal_line_for_43_record(board_root):
    r = dispatch("save_decision_map", {"map": _valid_map(), "slug": "x", "n": 100})
    jl = r["journal_line"]
    assert jl.startswith("- Прогноз: 📐")             # готовая строка записи §4.3
    assert "(карта: decisions/" in jl and r["path"] in jl
    assert r["predicted"] in jl


def test_save_only_on_consent_directive(board_root):
    r = dispatch("save_decision_map", {"map": _valid_map(), "slug": "y", "n": 100})
    assert "соглас" in r["note"].lower()              # директива: только с согласия юзера


def test_save_without_slug_falls_back(board_root):
    # кириллический question не даёт латинского слага → детерминированный fallback
    r = dispatch("save_decision_map", {"map": _valid_map(), "n": 100})
    assert r["ok"] and re.fullmatch(r"decisions/\d{4}-\d{2}-\d{2}-decision\.json", r["path"])


def test_save_collision_gets_suffix_not_overwrite(board_root):
    a = dispatch("save_decision_map", {"map": _valid_map(), "slug": "same", "n": 100})
    b = dispatch("save_decision_map", {"map": _valid_map(), "slug": "same", "n": 100})
    assert a["path"] != b["path"]
    assert (board_root / a["path"]).is_file() and (board_root / b["path"]).is_file()


def test_save_refuses_invalid_map_no_write(board_root):
    m = _valid_map()
    m["uncertainties"][0]["confirmed_by_user"] = False
    r = dispatch("save_decision_map", {"map": m, "slug": "bad", "n": 100})
    assert "error" in r and r["errors"]
    assert not (board_root / "decisions").exists()    # fail-closed: ничего не записано


@pytest.mark.parametrize("bad", [
    "../x",                       # traversal
    "..",                         # traversal (чистый)
    "/etc/cron.d/pwn",            # абсолютный путь
    "\\windows\\x",               # windows-сепараторы
    "карта-решения",              # unicode вне [a-z0-9-]
    "Ship-Or-Wait",               # верхний регистр
    "a b",                        # пробел
    "a_b",                        # подчёркивание
    "",                           # пустой
    "-lead",                      # ведущий дефис (флаго-подобный)
])
def test_save_slug_attacks_rejected(board_root, bad):
    r = dispatch("save_decision_map", {"map": _valid_map(), "slug": bad, "n": 100})
    assert "error" in r and _has_cyrillic(r["error"])
    assert not (board_root / "decisions").exists()    # отказ ДО любой записи


def test_save_slug_non_string_rejected(board_root):
    r = dispatch("save_decision_map", {"map": _valid_map(), "slug": 42, "n": 100})
    assert "error" in r and not (board_root / "decisions").exists()
