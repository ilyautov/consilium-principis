"""decision_record.py — протокол заседания (board minutes) как ВЫХОД совета, ноль LLM.

МОАТ-ИНВАРИАНТ: тиры верности (🔵/🟢/🟡) в записи текут ТОЛЬКО из маркеров, уже
проставленных в session (гейтом). build_record копирует маркер as-is — никогда не
изобретает и не поднимает тир. Session, где все мнения 🟡, не может дать 🔵 в записи.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from decision_record import build_record
from session_render import render_decision_record


def _session_mixed():
    return {
        "question": "Уйти в свой продукт или остаться в найме?",
        "advisors": [
            {"name": "Марк Аврелий", "opinions": [
                {"marker": "blue", "argument": "Смотри на то, что в твоей власти.",
                 "quote": {"text": "Confine thyself to the present.", "source": "Meditations 7.29"}},
                {"marker": "yellow", "argument": "Вероятно, он бы посоветовал не спешить."},
            ]},
            {"name": "Макиавелли", "opinions": [
                {"marker": "green", "argument": "Взвесь фortune и virtù прежде чем прыгать."},
            ]},
        ],
        "disagreement": {"axis": "Скорость решения", "sides": ["рискни сейчас", "жди сигнала"],
                          "resolver": "проверь малым шагом"},
        "synthesis": "Проверь гипотезу малым шагом, не сжигая мостов.",
        "decision": {"status": "approve_with_conditions"},
        "re_review_triggers": ["если трекшен не появится за 2 недели"],
    }


def _session_all_yellow():
    return {
        "question": "Стоит ли масштабировать сейчас?",
        "advisors": [
            {"name": "Советник A", "opinions": [
                {"marker": "yellow", "argument": "Вероятно, рано."},
            ]},
            {"name": "Советник B", "opinions": [
                {"marker": "yellow", "argument": "Похоже, стоит подождать."},
            ]},
        ],
        "synthesis": "Подождать сигнала.",
    }


def _session_all_blue():
    return {
        "question": "Что важно?",
        "advisors": [
            {"name": "Аврелий", "opinions": [
                {"marker": "blue", "argument": "Держи фокус.",
                 "quote": {"text": "Confine thyself.", "source": "Meditations 7.29"}},
            ]},
        ],
        "synthesis": "Держи фокус.",
    }


# ---------- build_record: базовая форма и текучесть тиров ----------

def test_build_record_positions_carry_source_markers_verbatim():
    rec = build_record(_session_mixed())
    assert rec["question"] == "Уйти в свой продукт или остаться в найме?"
    names = {p["advisor"] for p in rec["positions"]}
    assert names == {"Марк Аврелий", "Макиавелли"}
    aurelius = next(p for p in rec["positions"] if p["advisor"] == "Марк Аврелий")
    tiers = {a["tier"] for a in aurelius["assumptions"]}
    assert tiers == {"🔵", "🟡"}
    machiavelli = next(p for p in rec["positions"] if p["advisor"] == "Макиавелли")
    assert machiavelli["assumptions"][0]["tier"] == "🟢"


def test_build_record_provenance_counts_markers_across_opinions():
    rec = build_record(_session_mixed())
    assert rec["provenance"] == {"blue": 1, "green": 1, "yellow": 1}


def test_build_record_stance_is_argument_summary():
    rec = build_record(_session_mixed())
    aurelius = next(p for p in rec["positions"] if p["advisor"] == "Марк Аврелий")
    assert "власти" in aurelius["stance"] or "спешить" in aurelius["stance"]


# ---------- MOAT TEST: тир никогда не поднимается / не изобретается ----------

def test_moat_all_yellow_session_yields_zero_blue_anywhere():
    rec = build_record(_session_all_yellow())
    all_tiers = [a["tier"] for p in rec["positions"] for a in p["assumptions"]]
    assert all_tiers, "ожидались допущения для проверки"
    assert "🔵" not in all_tiers
    assert rec["provenance"]["blue"] == 0
    assert set(all_tiers) <= {"🟡"}


def test_moat_blue_opinion_stays_blue_copied_not_invented():
    rec = build_record(_session_all_blue())
    tiers = [a["tier"] for p in rec["positions"] for a in p["assumptions"]]
    assert tiers == ["🔵"]
    assert rec["provenance"]["blue"] == 1


def test_moat_unknown_marker_not_counted_as_blue():
    session = {
        "question": "q",
        "advisors": [{"name": "X", "opinions": [
            {"marker": "violation", "argument": "нарушение"},
            {"marker": None, "argument": "без маркера"},
        ]}],
    }
    rec = build_record(session)
    assert rec["provenance"]["blue"] == 0
    assert rec["provenance"]["green"] == 0
    assert rec["provenance"]["yellow"] == 0


# ---------- dissent ----------

def test_dissent_extracted_from_disagreement():
    rec = build_record(_session_mixed())
    assert len(rec["dissent"]) == 2
    points = {d["point"] for d in rec["dissent"]}
    assert points == {"рискни сейчас", "жди сигнала"}


def test_dissent_empty_when_no_disagreement():
    rec = build_record(_session_all_blue())
    assert rec["dissent"] == []


# ---------- decision.status ----------

def test_decision_status_uses_explicit_field_when_valid():
    rec = build_record(_session_mixed())
    assert rec["decision"]["status"] == "approve_with_conditions"
    assert rec["decision"]["choice"] == "Проверь гипотезу малым шагом, не сжигая мостов."


def test_decision_status_defers_when_invalid_value():
    session = dict(_session_all_blue(), decision={"status": "yolo-approve"})
    rec = build_record(session)
    assert rec["decision"]["status"] == "defer"


def test_decision_no_synthesis_no_decision_is_honest_defer():
    session = {"question": "q", "advisors": []}
    rec = build_record(session)
    assert rec["decision"]["status"] == "defer"
    assert rec["decision"]["choice"] is None


def test_re_review_triggers_default_empty_list():
    session = {"question": "q", "advisors": [], "synthesis": "s"}
    rec = build_record(session)
    assert rec["re_review_triggers"] == []


def test_re_review_triggers_passed_through():
    rec = build_record(_session_mixed())
    assert rec["re_review_triggers"] == ["если трекшен не появится за 2 недели"]


# ---------- defensive: never crash ----------

def test_none_session_returns_honest_skeleton():
    rec = build_record(None)
    assert rec["question"] == ""
    assert rec["positions"] == []
    assert rec["dissent"] == []
    assert rec["decision"] == {"choice": None, "status": "defer"}
    assert rec["re_review_triggers"] == []
    assert rec["provenance"] == {"blue": 0, "green": 0, "yellow": 0}


def test_empty_dict_session_returns_skeleton():
    rec = build_record({})
    assert rec["question"] == ""
    assert rec["positions"] == []


def test_non_dict_session_returns_skeleton_no_crash():
    rec = build_record("не сессия, а строка")
    assert rec["question"] == ""
    assert rec["positions"] == []


def test_missing_advisors_key_safe():
    rec = build_record({"question": "q"})
    assert rec["positions"] == []


def test_malformed_advisor_entries_safe():
    session = {"question": "q", "advisors": [
        {"opinions": [{"marker": "blue", "argument": "x"}]},   # без name
        {"name": "Y"},                                          # без opinions
        "не словарь",                                           # мусор
        None,
    ]}
    rec = build_record(session)
    # не крашит; советник без name честно пропускается или получает пустое имя, но не рвёт вызов
    assert isinstance(rec["positions"], list)


# ---------- render_decision_record ----------

def test_render_contains_question_tiers_dissent_decision_provenance():
    rec = build_record(_session_mixed())
    md = render_decision_record(rec, surface="md")
    assert "Уйти в свой продукт" in md
    assert "🔵" in md and "🟢" in md and "🟡" in md
    assert "Диссент" in md or "Дисcент" in md or "возражени" in md.lower() or "Dissent" in md
    assert "approve_with_conditions" in md
    assert "🔵" in md.split("---")[-1] or "1🔵" in md or "1 🔵" in md  # provenance footer present


def test_render_no_dissent_shows_honest_no_objections_line():
    rec = build_record(_session_all_blue())
    md = render_decision_record(rec, surface="md")
    assert "явных возражений не зафиксировано" in md


def test_render_defer_decision_shown_honestly():
    rec = build_record({"question": "q", "advisors": []})
    md = render_decision_record(rec, surface="md")
    assert "defer" in md


# ---------- MCP dispatch ----------

def test_mcp_dispatch_decision_record_returns_record_and_content():
    from mcp_server import dispatch
    r = dispatch("decision_record", {"session": _session_mixed()})
    assert "record" in r and "content" in r
    assert r["record"]["question"] == "Уйти в свой продукт или остаться в найме?"
    assert "🔵" in r["content"]


def test_mcp_dispatch_decision_record_listed_in_tools():
    from mcp_server import list_tools
    names = {t["name"] for t in list_tools()}
    assert "decision_record" in names
