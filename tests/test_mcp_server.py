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


def test_load_source_rejects_consilium_runtime_log(tmp_path, monkeypatch):
    import mcp_server
    runtime_log = tmp_path / ".consilium" / "swallow.log"
    runtime_log.parent.mkdir()
    runtime_log.write_text("runtime details\n", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path=".consilium/swallow.log")


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
    assert "cite" in instr and "перефразир" in instr.lower()       # 🔵 через cite, не ручной пересказ
    assert "молча" in instr.lower()                                # тихая оркестрация (без тех-преамбулы)
    assert "уточняющих" in instr.lower() and "круглый стол" in instr.lower()  # живой интерактив до синтеза
    assert "первый" in instr.lower() and "kind=opening" in instr   # опенинг-виджет с первого кадра
    assert "дефект корпуса" in instr.lower()                       # запрет конфабуляции дефекта гейта


def test_instructions_rule18_moat_directives():
    import mcp_server as m
    assert "18." in m.INSTRUCTIONS
    for kw in ("ДИССЕНТ", "РЕЙМ-ЧЕК", "never_quote", "diversity_check", "эхо-камер"):
        assert kw in m.INSTRUCTIONS, "INSTRUCTIONS не несёт ров-директиву: %s" % kw


def test_handler_keyerror_not_mislabeled_as_unknown_tool(monkeypatch):
    # KeyError ВНУТРИ хендлера (напр. неполный объект) → -32603 «ошибка тула», НЕ -32601
    from mcp_server import _handle_rpc, TOOLS

    def _boom(**kw):
        raise KeyError("synthesis")

    monkeypatch.setitem(TOOLS, "_probe_boom", {
        "name": "_probe_boom", "description": "x",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "handler": _boom})
    r = _handle_rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "_probe_boom", "arguments": {}}})
    assert r["error"]["code"] == -32603
    assert "неизвестный тул" not in r["error"]["message"]


def test_unknown_tool_reports_unknown():
    from mcp_server import _handle_rpc
    r = _handle_rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                     "params": {"name": "no_such_tool", "arguments": {}}})
    assert r["error"]["code"] == -32601 and "неизвестн" in r["error"]["message"]


def test_rpc_error_hides_absolute_paths(monkeypatch, capsys):
    # Текст исключения может нести абсолютный путь (FileNotFoundError и т.п.) — хосту
    # уходит обобщённое сообщение, деталь остаётся в stderr сервера.
    from mcp_server import _handle_rpc, TOOLS

    def _boom(**kw):
        raise ValueError("/secret/path/leaked")

    monkeypatch.setitem(TOOLS, "_probe_leak", {
        "name": "_probe_leak", "description": "x",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "handler": _boom})
    r = _handle_rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                     "params": {"name": "_probe_leak", "arguments": {}}})
    assert r["error"]["code"] == -32603
    assert "/secret/path" not in r["error"]["message"]
    assert "/secret/path" in capsys.readouterr().err          # деталь — в stderr


def test_retrieve_attaches_verbatim_quoting_hint():
    # point-of-use: выдача retrieve несёт директиву «цитируй text дословно», гасит конфабуляцию 🟡
    import os
    adv = os.path.join(ROOT, "lenses", "strategist")
    r = dispatch("retrieve", {"query": "deception in war", "advisor_dir": adv})
    assert "passages" in r and isinstance(r["passages"], list)
    assert "дословно" in r["how_to_quote"].lower() and "🟡" in r["how_to_quote"]


def test_retrieve_rejects_oversize_top_k_before_retrieval(tmp_path, monkeypatch):
    import mcp_server as m
    from engine import retrieval

    calls = []

    def spy(query, advisor_dir, top_k=3):
        calls.append(top_k)
        return []

    monkeypatch.setattr(retrieval, "retrieve", spy)
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    monkeypatch.setenv("CONSILIUM_JUDGE_BACKEND", "host")
    (tmp_path / "advisors" / "a").mkdir(parents=True)

    rejected = m._retrieve("q", "advisors/a", top_k=33)
    assert "error" in rejected
    assert calls == []

    accepted = m._retrieve("q", "advisors/a", top_k=32)
    assert accepted["passages"] == []
    assert calls == [32]


def test_retrieve_and_cite_reject_over_byte_cap_queries_before_retrieval(tmp_path, monkeypatch):
    """Невалидный UTF-8 payload отсекается до импорта/вызова retrieval."""
    import mcp_server as m
    from engine import retrieval

    calls = []
    monkeypatch.setattr(retrieval, "retrieve",
                        lambda *args, **kwargs: calls.append(args) or [])
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    adv = tmp_path / "adv"
    adv.mkdir()
    (adv / "corpus.jsonl").write_text("", encoding="utf-8")
    oversize = "x" * (m._MAX_QUERY_BYTES + 1)

    assert "error" in m._retrieve(oversize, "adv")
    cited = m._cite("adv", oversize, use_kernels=False)
    assert cited["quotes"] == [] and cited["marker"] == "🟡" and "error" in cited
    assert calls == []


def test_cite_rejects_more_than_eight_queries_without_iterating_items(tmp_path, monkeypatch):
    """Проверка количества идёт до обхода списка: не материализуем атакующий payload."""
    import mcp_server as m

    class PoisonedList(list):
        def __iter__(self):
            raise AssertionError("oversize query list must not be iterated")

    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    adv = tmp_path / "adv"
    adv.mkdir()
    (adv / "corpus.jsonl").write_text("", encoding="utf-8")

    result = m._cite("adv", PoisonedList(["q"] * (m._MAX_CITE_QUERIES + 1)), use_kernels=False)
    assert result["quotes"] == [] and result["marker"] == "🟡" and "error" in result


def test_cite_returns_ready_verified_quotes():
    # детерминированный рычаг рва: cite отдаёт ГОТОВЫЕ проверенные объекты, хост не пишет текст сам
    r = dispatch("cite", {"advisor_dir": STRAT, "query": "deception in war"})
    assert r["quotes"] and r["best"]["marker"] in ("🔵", "🟢")
    for q in r["quotes"]:                          # КАЖДАЯ возвращённая цитата реально дословна
        fc = dispatch("fidelity_check", {"quote": q["text"], "advisor_dir": STRAT})
        assert fc["verbatim"] is True and fc["status"] == q["marker"]


def test_cite_accepts_query_list_for_multiquery_recall():
    # recall-рычаг: хост шлёт список англ. формулировок (мульти-запрос продакшн-формы)
    r = dispatch("cite", {"advisor_dir": STRAT,
                          "query": ["deception in war", "knowing the enemy and yourself"]})
    assert all(q["text"] for q in r["quotes"])     # пул из нескольких запросов, дедуп, все дословны


def test_cite_no_match_returns_empty_not_fabrication():
    r = dispatch("cite", {"advisor_dir": STRAT,
                          "query": "рецепт борща", "use_kernels": False})
    if not r["quotes"]:
        assert r["marker"] == "🟡" and "выдумывай" in r["note"].lower()
    else:
        for q in r["quotes"]:
            fc = dispatch("fidelity_check", {"quote": q["text"], "advisor_dir": STRAT})
            assert fc["verbatim"] is True          # никогда не возвращает невериф. текст


def test_cite_registered_and_in_instructions():
    assert "cite" in {t["name"] for t in list_tools()}
    from mcp_server import INSTRUCTIONS
    assert "cite" in INSTRUCTIONS


def test_build_lens_tool_grounds_and_is_citable(monkeypatch, tmp_path):
    # сквозной: build_lens → корпус → cite отдаёт 🔵 из текста-основы, прочтение остаётся 🟡
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))   # write-гард: корень=tmp
    dest = str(tmp_path / "test-lens")
    r = dispatch("build_lens", {
        "name": "Тест-линза", "dest": dest, "kind": "personality",
        "ground_text": "All warfare is based on deception, says the canon of strategy.",
        "reading_notes": "Я читаю это как разрешение на асимметрию, а не на ложь людям."})
    assert r["tiers"].get("P1", 0) >= 1 and r["tiers"].get("U1", 0) >= 1
    assert "build_lens" in {t["name"] for t in list_tools()}
    c = dispatch("cite", {"advisor_dir": dest, "query": "warfare deception"})
    assert c["quotes"] and c["best"]["marker"] == "🔵"        # слова источника цитируются дословно
    # фраза из прочтения — НЕ дословный авторский тир
    fc = dispatch("fidelity_check", {"quote": "разрешение на асимметрию", "advisor_dir": dest})
    assert fc["status"] != "🔵"


def test_build_lens_grounds_from_url(monkeypatch, tmp_path):
    # основа линзы — целый PD-том по URL (фетч+strip), без вставки текста
    import collect_common as cc
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))   # write-гард: корень=tmp
    monkeypatch.setattr(cc, "fetch", lambda url, timeout=30:
                        "*** START OF THE PROJECT GUTENBERG EBOOK ***\n"
                        "He who is feared is safer than he who is loved, in the council of princes.\n"
                        "*** END OF THE PROJECT GUTENBERG EBOOK ***")
    dest = str(tmp_path / "url-lens")
    r = dispatch("build_lens", {"name": "URL-линза", "dest": dest, "kind": "personality",
                 "ground_url": "https://www.gutenberg.org/cache/epub/1/pg1.txt",
                 "reading_notes": "Читаю про надёжность стимула."})
    assert r["tiers"].get("P1", 0) >= 1
    fc = dispatch("fidelity_check", {"quote": "He who is feared is safer", "advisor_dir": dest})
    assert fc["status"] == "🔵"                          # дословно из фетченного тома
    ground = open(os.path.join(dest, "sources", "ground.txt"), encoding="utf-8").read()
    assert "START OF THE PROJECT GUTENBERG" not in ground   # Gutenberg-boilerplate срезан до сборки


def test_build_lens_requires_some_ground(tmp_path):
    r = dispatch("build_lens", {"name": "пусто", "dest": str(tmp_path / "x")})
    assert "error" in r and "основу" in r["error"]


def test_build_lens_path_traversal_guarded(tmp_path):
    r = dispatch("build_lens", {"name": "t", "dest": str(tmp_path / "y"),
                 "ground_path": "../../../../../../etc/passwd"})
    assert "error" in r and ("traversal" in r["error"].lower() or "вне корня" in r["error"])


def test_build_lens_in_instructions():
    from mcp_server import INSTRUCTIONS
    assert "build_lens" in INSTRUCTIONS and "выспрашивается" in INSTRUCTIONS.lower()


def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        dispatch("nonexistent_tool", {})


# ── §4.3 петля исхода (минимум): loop_status без леджера + outcome_nudge после синтеза ──

_JOURNAL_PENDING = "## Журнал решений\n### Форум-конфликт\n- **ИСХОД: ⏳ pending**\n"


def test_loop_status_without_ledger_reads_journal(tmp_path, monkeypatch):
    # старт новой сессии: хосту неоткуда взять ledger → тул сам читает существующий журнал
    import mcp_server
    (tmp_path / "principis.md").write_text(_JOURNAL_PENDING, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("loop_status", {})
    assert r["count"] == 1 and r["pending"][0]["title"] == "Форум-конфликт"
    assert "hint" in r and "исход" in r["hint"].lower()      # директива «вернись и закрой»


def test_loop_status_zero_pending_stays_quiet(tmp_path, monkeypatch):
    # ноль висящих → минимальный тихий ответ (не шумим в сессии, где юзер просто исследует)
    import mcp_server
    (tmp_path / "principis.md").write_text("### Цены\n- **ИСХОД: ✅**\n", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("loop_status", {})
    assert r["count"] == 0 and r["pending"] == [] and "hint" not in r


def test_loop_status_ledger_mode_is_backcompat():
    r = dispatch("loop_status", {"ledger": []})
    assert r["total"] == 0 and r["endorse_rate"] is None     # прежний контракт не тронут


_JOURNAL_WITH_FORECAST = ("## Журнал решений\n### Шипнуть\n"
                          "- Прогноз: 📐 P(лучший) 0.83 (карта: decisions/x.json)\n"
                          "- **ИСХОД: ⏳ pending**\n")


def test_loop_status_pending_carries_predicted_and_calibration_hint(tmp_path, monkeypatch):
    # Ф4 (§6): запись с прогнозом → pending-item несёт predicted, hint велит сравнить
    # прогноз и факт при резолюции (расхождение = калибровка, не провал)
    import mcp_server
    (tmp_path / "principis.md").write_text(_JOURNAL_WITH_FORECAST, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("loop_status", {})
    assert r["pending"][0]["predicted"].startswith("P(лучший) 0.83")
    assert "сравни" in r["hint"].lower() and "калибровка" in r["hint"].lower()
    assert "не провал" in r["hint"].lower()


def test_loop_status_hint_quiet_about_forecast_without_predicted(tmp_path, monkeypatch):
    # fail-closed: нет строки прогноза → нет поля predicted и нет калибровочного хвоста
    import mcp_server
    (tmp_path / "principis.md").write_text(_JOURNAL_PENDING, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("loop_status", {})
    assert "predicted" not in r["pending"][0]
    assert "калибровка" not in r["hint"].lower()


def test_board_status_pending_carries_predicted(tmp_path, monkeypatch):
    # board_status использует тот же сёрфейсер → predicted виден и на старте сессии
    import mcp_server
    (tmp_path / "principis.md").write_text(_JOURNAL_WITH_FORECAST, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("board_status", {})
    assert r["pending_outcomes"][0]["predicted"].startswith("P(лучший) 0.83")


def test_render_session_synthesis_carries_outcome_nudge():
    # естественный момент «синтез выдан» → point-of-use нудж записать решение (один раз)
    s = {"question": "q", "synthesis": "вердикт",
         "advisors": [{"name": "М", "opinions": [{"marker": "yellow", "argument": "a"}]}]}
    w = dispatch("render_session", {"session": s, "surface": "widget"})
    assert "outcome_nudge" in w and "журнал" in w["outcome_nudge"].lower()
    assert "ИСХОД: ⏳" in w["outcome_nudge"]                  # шаблон записи прямо в директиве
    assert "не повторяй" in w["outcome_nudge"].lower()        # ненавязчивость — часть директивы
    md = dispatch("render_session", {"session": s, "surface": "md"})
    assert "outcome_nudge" in md                              # нудж не зависит от surface


def test_render_session_no_nudge_before_synthesis():
    # круглый стол ещё идёт (нет synthesis) или опенинг → нуджа НЕТ (не шумим на каждый ход)
    s = {"question": "q", "questions": ["что болит?"],
         "advisors": [{"name": "М", "opinions": [{"marker": "yellow", "argument": "a"}]}]}
    assert "outcome_nudge" not in dispatch("render_session", {"session": s, "surface": "widget"})
    o = dispatch("render_session", {"session": {"advisors": [{"name": "М"}]},
                                    "surface": "widget", "kind": "opening"})
    assert "outcome_nudge" not in o


def test_board_status_surfaces_pending_outcomes(tmp_path, monkeypatch):
    # старт сессии = board_status (правило 9) → висящие решения видны сразу
    import mcp_server
    (tmp_path / "principis.md").write_text(_JOURNAL_PENDING, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("board_status", {})
    assert [p["title"] for p in r["pending_outcomes"]] == ["Форум-конфликт"]
    assert "loop_nudge" in r


def test_board_status_quiet_without_pending(tmp_path, monkeypatch):
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("board_status", {})
    assert "pending_outcomes" not in r and "loop_nudge" not in r   # ноль висящих → как раньше


def test_outcome_loop_round_trip_record_status_resolve(tmp_path, monkeypatch):
    # полный круг: синтез → нудж (шаблон) → хост записал → loop_status видит ⏳ →
    # юзер закрыл исход → loop_status снова тихий
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    j = tmp_path / "principis.md"
    j.write_text("## Журнал решений\n", encoding="utf-8")
    s = {"question": "выходить ли из спора", "synthesis": "выйти",
         "advisors": [{"name": "М", "opinions": [{"marker": "yellow", "argument": "a"}]}]}
    nudge = dispatch("render_session", {"session": s, "surface": "md"})["outcome_nudge"]
    assert "ИСХОД: ⏳" in nudge
    j.write_text(j.read_text(encoding="utf-8") +
                 "\n### 2026-07-02 · выйти из спора\n- Решение: выйти\n- Почему: не моя игра\n"
                 "- **ИСХОД: ⏳ pending**\n", encoding="utf-8")
    st = dispatch("loop_status", {})
    assert st["count"] == 1 and "2026-07-02" in st["pending"][0]["title"]
    j.write_text(j.read_text(encoding="utf-8").replace(
        "**ИСХОД: ⏳ pending**", "**ИСХОД: ✅** — сработало. Одобрено: да"), encoding="utf-8")
    st2 = dispatch("loop_status", {})
    assert st2["count"] == 0 and "hint" not in st2


def test_outcome_loop_in_instructions():
    from mcp_server import INSTRUCTIONS
    assert "outcome_nudge" in INSTRUCTIONS and "loop_status" in INSTRUCTIONS


def test_instructions_has_ondemand_citation_transparency():
    """Rule 7 несёт on-demand прозрачность: по запросу юзера показать source_ref + честное воздержание."""
    from mcp_server import INSTRUCTIONS
    assert "ПРОЗРАЧНОСТЬ ПО ЗАПРОСУ" in INSTRUCTIONS
    assert "покажи, что проверено" in INSTRUCTIONS
    assert "source_ref" in INSTRUCTIONS
    assert "НЕ выдумывай" in INSTRUCTIONS or "не выдумывай источники" in INSTRUCTIONS


def test_cite_query_list_capped(tmp_path, monkeypatch):
    # DoS-кап (M2): 50 формулировок в списке → внутренний пул запросов режется до 8.
    # Наблюдаемый контракт: _cite не делает >8 retrieve-проходов — патчим retrieve счётчиком.
    import mcp_server as m
    from engine import retrieval
    calls = {"n": 0}
    def counting(q, adv, top_k=6):
        calls["n"] += 1
        return []
    monkeypatch.setattr(retrieval, "retrieve", counting)
    adv = tmp_path / "adv"; adv.mkdir()
    (adv / "corpus.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    m._cite("adv", ["q%d" % i for i in range(50)])
    assert calls["n"] <= 8


def test_cite_top_k_clamped_and_numeric_garbage_fails_closed(tmp_path, monkeypatch):
    # DoS-кап (M2): top_k=10**6 клампится к ≤32 (наблюдаемо через подменённый retrieve),
    # мусор в числовых параметрах → fail-closed 🟡 без исключения.
    import mcp_server as m
    from engine import retrieval
    seen = {"top_k": None}
    def spy(q, adv, top_k=6):
        seen["top_k"] = top_k
        return []
    monkeypatch.setattr(retrieval, "retrieve", spy)
    adv = tmp_path / "adv"; adv.mkdir()
    (adv / "corpus.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    m._cite("adv", "anything", top_k=10**6)
    assert seen["top_k"] is not None and seen["top_k"] <= 32
    r = m._cite("adv", "anything", top_k="junk")
    assert r["quotes"] == [] and r["marker"] == "🟡"
    r = m._cite("adv", "anything", limit="junk")
    assert r["quotes"] == [] and r["marker"] == "🟡"
