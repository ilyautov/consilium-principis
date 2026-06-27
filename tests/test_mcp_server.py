"""Тонкий MCP-слой над скриптами: Consilium = сервер контекста+инструментов, не модель.

Ризонинг арендуем у вызывающей сети; MCP отдаёт чистый контекст + гейт. Тут — ЧИСТОЕ ядро
(реестр тулов + dispatch), без зависимости от MCP SDK (транспорт — отдельно, в __main__).
Ключевой тул — fidelity_check: это протокол-гейт. Хост ОБЯЗАН звать его и воздержаться на 🟡.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pytest
from mcp_server import list_tools, dispatch

STRAT = os.path.join(ROOT, "lenses", "strategist")


def test_list_tools_exposes_core_set():
    names = {t["name"] for t in list_tools()}
    assert {"fidelity_check", "retrieve", "situation_analyze",
            "governance_verify", "calibrate"} <= names
    for t in list_tools():
        assert t["description"]
        assert "input_schema" in t and t["input_schema"]["type"] == "object"


def test_fidelity_check_passes_canon_quote_as_blue():
    r = dispatch("fidelity_check", {"quote": "All warfare is based on deception.",
                                    "advisor_dir": STRAT})
    assert r["status"] == "🔵" and r["source"]      # дословная максима канона


def test_fidelity_check_fabrication_is_yellow_protocol_gate():
    r = dispatch("fidelity_check", {"quote": "Сунь-цзы обожал мороженое по воскресеньям.",
                                    "advisor_dir": STRAT})
    assert r["status"] == "🟡" and r["verbatim"] is False   # хост ОБЯЗАН воздержаться


def test_situation_analyze_from_json_tree():
    tree = {"move": None, "children": [
        {"move": {"by": "you", "claim": "довод", "grounded": True, "strength": 0.6},
         "children": [{"move": {"by": "opponent", "claim": "контр",
                                "grounded": True, "strength": 0.3}}]}]}
    r = dispatch("situation_analyze",
                 {"tree": tree, "opponent": "person", "stance": "competitive"})
    assert r["verdict"] == "winnable" and r["value"] > 0
    assert r["principal_variation"] == ["довод", "контр"]   # claims строками


def test_situation_analyze_fabrication_does_not_win():
    tree = {"move": None, "children": [
        {"move": {"by": "you", "claim": "блеф", "grounded": False, "strength": 9.9}}]}
    r = dispatch("situation_analyze", {"tree": tree})
    assert r["value"] == 0.0 and r["verdict"] == "no_winning_line"


def test_situation_stress_test_reports_fragility():
    tree = {"move": None, "children": [
        {"move": {"by": "you", "claim": "довод", "grounded": True, "strength": 0.8},
         "children": [{"move": {"by": "opponent", "claim": "слабый",
                                "grounded": True, "strength": 0.2}}]}]}
    r = dispatch("situation_stress_test", {"tree": tree, "perturbations": [
        {"kind": "invalidate", "claim": "довод"},
        {"kind": "inject_counter", "claim": "killer", "strength": 0.99}]})
    assert r["baseline_verdict"] == "winnable"
    assert r["robustness"] == 0.0 and len(r["fragile_under"]) == 2


def test_governance_verify_intact_corpus():
    r = dispatch("governance_verify", {"path": STRAT})
    assert r["ok"] is True
    assert len(r["head"]) == 64                    # sha256 hex
    assert r["tiers"].get("P1", 0) == 31


def test_calibrate_recommends_framing():
    log = "### r\n- Подача: светлый\n- **ИСХОД: ✅**\n- Одобрено задним числом: да\n"
    r = dispatch("calibrate", {"log_text": log})
    assert r["recommend"] in ("light", "dark")
    assert "capture_flag" in r


def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        dispatch("nonexistent_tool", {})
