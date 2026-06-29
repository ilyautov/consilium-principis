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


def test_relative_advisor_dir_resolves_regardless_of_cwd(tmp_path, monkeypatch):
    # БРИДЖ Cowork: Claude Desktop спавнит сервер с НЕОПРЕДЕЛЁННЫМ cwd. Относительный путь
    # обязан резолвиться от корня репо, иначе контур молча уйдёт в 🟡 (бесполезен).
    monkeypatch.chdir(tmp_path)                       # cwd ≠ корень репо
    r = dispatch("fidelity_check", {"quote": "All warfare is based on deception.",
                                    "advisor_dir": "lenses/strategist"})
    assert r["status"] == "🔵"                         # нашёл корпус несмотря на чужой cwd


def test_long_tool_returns_job_and_completes(monkeypatch):
    # долгие тулы рвали таймаут MCP → теперь фоновый джоб: job_id сразу, job_status опрашивается
    import mcp_server, time
    monkeypatch.setattr(mcp_server, "_do_seed", lambda: {"results": ["ok"]})
    started = dispatch("seed_council", {})
    assert started["status"] == "running" and started["job_id"]
    deadline = time.time() + 5
    st = dispatch("job_status", {"job_id": started["job_id"]})
    while st["status"] == "running" and time.time() < deadline:
        time.sleep(0.02)
        st = dispatch("job_status", {"job_id": started["job_id"]})
    assert st["status"] == "done" and st["result"] == {"results": ["ok"]}


def test_job_error_is_captured(monkeypatch):
    import mcp_server, time
    def boom():
        raise RuntimeError("сеть упала")
    monkeypatch.setattr(mcp_server, "_do_seed", boom)
    jid = dispatch("seed_council", {})["job_id"]
    deadline = time.time() + 5
    st = dispatch("job_status", {"job_id": jid})
    while st["status"] == "running" and time.time() < deadline:
        time.sleep(0.02)
        st = dispatch("job_status", {"job_id": jid})
    assert st["status"] == "error" and "сеть упала" in st["error"]


def test_job_status_unknown_id():
    assert "error" in dispatch("job_status", {"job_id": "job-999999"})


def test_lifecycle_tools_exposed_for_shell_free_hosts():
    # весь цикл сборки доступен как MCP-тулы → чистый MCP-хост (Cowork) не выходит в шелл
    names = {t["name"] for t in list_tools()}
    assert {"doctor", "build_advisor", "seed_council",
            "ingest_telegram", "setup_full", "job_status"} <= names


def test_doctor_tool_runs_readonly():
    r = dispatch("doctor", {})
    assert "healthy" in r and isinstance(r["checks"], list)
    assert any(c["name"] == "python" for c in r["checks"])


def test_render_session_tool_emits_surfaces():
    s = {"question": "q", "synthesis": "s",
         "advisors": [{"name": "Макиавелли",
                       "opinions": [{"marker": "blue", "argument": "a"}]}]}
    md = dispatch("render_session", {"session": s, "surface": "md"})
    assert md["surface"] == "md" and "Макиавелли" in md["content"]
    w = dispatch("render_session", {"session": s, "surface": "widget"})
    assert "sendPrompt(" in w["content"] and "--color-text-info" in w["content"]
    assert "show_widget" in w["next_action"]        # директива в point-of-use тянет хост к рендеру
    assert "next_action" not in dispatch("render_session", {"session": s, "surface": "md"})
    assert "render_session" in {t["name"] for t in list_tools()}


def test_list_recipes_widget_surface_is_clickable():
    r = dispatch("list_recipes", {"surface": "widget"})
    assert r["surface"] == "widget" and "sendPrompt(" in r["content"]
    assert "recipes" in dispatch("list_recipes", {})        # дефолт = сырые данные


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


def test_atomic_grounding_exposes_inflation():
    text = "All warfare is based on deception. Сунь-цзы обожал мороженое по воскресеньям."
    r = dispatch("atomic_grounding", {"text": text, "advisor_dir": STRAT})
    assert r["atom_level"] == 0.5 and abs(r["inflation"] - 0.5) < 1e-9


def test_mirror_report_via_dispatch():
    r = dispatch("mirror_report", {
        "stated": [{"when": "x", "vector": "хочу роста бизнеса"}],
        "decisions": [{"theme": "люди", "endorsed": True}]})
    assert r["aligned"] is False and r["sufficient"] is True


def test_premortem_via_dispatch_untrusted_without_history():
    r = dispatch("premortem", {"scenarios": [{"label": "a", "value": 0.5, "prob": 1.0}]})
    assert r["trustworthy"] is False


def test_advisor_weights_via_dispatch():
    r = dispatch("advisor_weights", {"records": [
        {"advisor": "a", "outcome": "good", "endorsed": True},
        {"advisor": "b", "outcome": "bad", "endorsed": False}]})
    assert r["weights"]["a"] > r["weights"]["b"]


def test_pending_outcomes_via_dispatch():
    r = dispatch("pending_outcomes", {"journal_text":
                 "### A\n- **ИСХОД: ⏳ pending**\n### B\n- **ИСХОД: ✅**\n"})
    assert r["pending"] == ["A"]


def test_stability_via_dispatch():
    r = dispatch("stability", {"verdicts": ["winnable", "winnable", "winnable"]})
    assert r["label"] == "robust"


def test_board_status_reports_next_step():
    r = dispatch("board_status", {})
    assert "next_step" in r and "action" in r["next_step"]
    assert "advisors" in r["preflight"]


def test_scaffold_principis_via_dispatch():
    r = dispatch("scaffold_principis", {"answers": {"who": "Илья", "interface_mode": "rigor"}})
    assert "interface_mode: rigor" in r["markdown"]
    assert "ПРОБЕЛ" in r["markdown"]            # вектор не дан → держим живым


def test_initialize_exposes_instructions_to_host():
    # ЕДИНСТВЕННЫЙ канал правил для MCP-хоста (Cowork НЕ читает SKILL.md): server instructions.
    from mcp_server import _handle_rpc
    r = _handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    instr = r["result"]["instructions"]
    assert "show_widget" in instr and "render_session" in instr   # рендер-контракт дошёл до хоста
    assert "fidelity_check" in instr and "🔵" in instr            # протокол-гейт верности
    assert "согласие" in instr.lower() or "захват" in instr.lower()  # non-capture


def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        dispatch("nonexistent_tool", {})
