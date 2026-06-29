#!/usr/bin/env python3
"""Тонкий MCP-слой: Consilium-Principis = сервер контекста+инструментов, не модель.

Ризонинг (играть советников, строить дерево спора, синтез) арендуется у ВЫЗЫВАЮЩЕЙ сети
(Claude/GPT/…). MCP отдаёт чистый контекст + гейт. Архитектурный размен: контур переезжает
из hard-gate (движок не сгенерит фейк) в PROTOCOL-gate — хост ОБЯЗАН звать fidelity_check и
воздержаться на 🟡. Портативно (любая модель), но ров держится на честности хоста к протоколу.

Тулы (тонкие обёртки чистых функций):
  • fidelity_check  — цитата → 🔵/🟢/🟡 (ПРОТОКОЛ-ГЕЙТ: 🔵 только если тул подтвердил);
  • retrieve        — grounded-пассажи корпуса (чистый контекст);
  • situation_analyze — ситуационная карта (дерево путей + контрмеры + честный вердикт);
  • governance_verify — целостность корпуса (hash-chain) + отпечаток;
  • calibrate       — рекомендация подачи по журналу решений (+ guardrail захвата).

Ядро (list_tools/dispatch) НЕ зависит от MCP SDK → тестируемо. Транспорт (stdio JSON-RPC) —
в __main__, тонкий; при желании заменяется официальным SDK, дёргающим тот же dispatch.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.fidelity import best_match
from situation import Move, node, analyze
from governance import _verify_corpus
from calibration import calibrate as _calibrate_fn, parse_decision_log
from corpusbuild.paths import corpus_path


# ───────────────────────── обёртки чистых функций ─────────────────────────

def _fidelity_check(quote, advisor_dir):
    """Протокол-гейт: наиболее авторитетный тир дословного матча → маркер."""
    m = best_match(quote, advisor_dir)
    if not m:
        return {"status": "🟡", "verbatim": False, "source": ""}
    tier, src = m
    if tier in ("P1", "P2"):
        return {"status": "🔵", "verbatim": True, "source": src}
    if tier in ("S1", "S2"):
        return {"status": "🟢", "verbatim": True, "source": src}
    return {"status": "🟡", "verbatim": False, "source": ""}


def _retrieve(query, advisor_dir, top_k=3):
    import eval as _eval                     # ленивый импорт (тянет corpusbuild/engine)
    return _eval.retrieve(query, advisor_dir, top_k=top_k)


def _build_tree(d):
    """JSON-узел → внутреннее дерево ситуации (Move/node)."""
    mv = d.get("move")
    move = None
    if mv is not None:
        move = Move(mv["by"], mv.get("claim", ""), grounded=mv.get("grounded", False),
                    strength=mv.get("strength", 0.0), concession=mv.get("concession", False))
    return node(move, [_build_tree(c) for c in d.get("children", [])])


def _situation_analyze(tree, opponent="person", stance="competitive"):
    res = analyze(_build_tree(tree), opponent=opponent, stance=stance)
    res["principal_variation"] = [m.claim for m in res["principal_variation"]]  # JSON-сериализуемо
    return res


def _situation_stress_test(tree, perturbations, stance="competitive"):
    from perturbation import stress_test
    return stress_test(_build_tree(tree), perturbations, stance=stance)


def _governance_verify(path):
    cj = path if path.endswith(".jsonl") else corpus_path(path)
    res = _verify_corpus(cj)
    return res if res is not None else {"ok": False, "error": f"нет corpus.jsonl: {cj}"}


def _calibrate(log_text):
    return _calibrate_fn(parse_decision_log(log_text))


def _capture_situation(text):
    from extractor import capture_situation
    return capture_situation(text)


def _mirror_report(stated, decisions):
    from mirror import mirror_report
    return mirror_report(stated, decisions)


def _premortem(scenarios, ledger=None):
    from premortem import premortem
    return premortem(scenarios, ledger=ledger)


def _atomic_grounding(text, advisor_dir):
    from atomic import inflation_gap
    return inflation_gap(text, advisor_dir)


def _advisor_weights(records):
    from advisor_calibration import advisor_scores, vote_weights
    return {"scores": advisor_scores(records), "weights": vote_weights(records)}


def _stability(verdicts):
    from stability import stability
    return stability(verdicts)


def _pending_outcomes(journal_text):
    from outcome_loop import pending_from_journal
    return {"pending": pending_from_journal(journal_text)}


def _loop_status(ledger):
    from outcome_loop import loop_status
    return loop_status(ledger)


def _board_status():
    from preflight import preflight
    from scaffold import next_step
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pf = preflight(root)
    return {"preflight": pf, "next_step": next_step(pf)}


def _scaffold_principis(answers):
    from scaffold import scaffold_principis
    return {"markdown": scaffold_principis(answers)}


def _list_recipes():
    from recipes import load_recipes
    return {"recipes": load_recipes()}


def _validate_manifest(advisor_dir):
    from manifest_builder import validate_manifest
    import json as _json
    sd = os.path.join(advisor_dir, "sources")
    mp = os.path.join(sd, "manifest.json")
    if not os.path.isfile(mp):
        return {"ok": True, "problems": [], "note": "нет манифеста → всё P1 (бэк-компат)"}
    return validate_manifest(_json.load(open(mp, encoding="utf-8")), sd)


# ───────────────────────── реестр тулов ─────────────────────────

def _obj(props, required):
    return {"type": "object",
            "properties": {k: {"type": v} for k, v in props.items()},
            "required": required}


TOOLS = {
    "fidelity_check": {
        "description": "Протокол-гейт контура: проверить, дословна ли цитата в корпусе советника "
                       "→ 🔵 (P1/P2) / 🟢 (S1/S2) / 🟡 (не найдено). Помечать 🔵 ТОЛЬКО при 🔵 отсюда.",
        "input_schema": _obj({"quote": "string", "advisor_dir": "string"},
                             ["quote", "advisor_dir"]),
        "handler": _fidelity_check,
    },
    "retrieve": {
        "description": "Grounded-пассажи из корпуса советника под запрос (чистый контекст для ризонинга).",
        "input_schema": {"type": "object",
                         "properties": {"query": {"type": "string"},
                                        "advisor_dir": {"type": "string"},
                                        "top_k": {"type": "integer"}},
                         "required": ["query", "advisor_dir"]},
        "handler": _retrieve,
    },
    "capture_situation": {
        "description": "Захват контекста: сырой дамп (чат-лог конфликта/описание решения) → "
                       "структура (акторы, реплики, явные вопросы). Вход для карты и рейм-чека.",
        "input_schema": _obj({"text": "string"}, ["text"]),
        "handler": _capture_situation,
    },
    "situation_analyze": {
        "description": "Ситуационная карта: оценить дерево ходов (ты+оппонент). Возвращает оценку, "
                       "главную линию, ЧЕСТНЫЙ вердикт. opponent∈{self,person,world}, "
                       "stance∈{competitive,cooperative}. Фабрикацией (grounded:false) не выигрывают.",
        "input_schema": {"type": "object",
                         "properties": {"tree": {"type": "object"},
                                        "opponent": {"type": "string"},
                                        "stance": {"type": "string"}},
                         "required": ["tree"]},
        "handler": _situation_analyze,
    },
    "situation_stress_test": {
        "description": "Adversarial-стресс-тест карты: держится ли линия под возмущениями мира "
                       "(invalidate/weaken/inject_counter). Даёт robustness и fragile_under. "
                       "Возмущает мир/позицию, НЕ уста советников.",
        "input_schema": {"type": "object",
                         "properties": {"tree": {"type": "object"},
                                        "perturbations": {"type": "array"},
                                        "stance": {"type": "string"}},
                         "required": ["tree", "perturbations"]},
        "handler": _situation_stress_test,
    },
    "governance_verify": {
        "description": "Целостность корпуса (Барсик hash-chain): подмена рвёт цепь. Даёт отпечаток-хеш "
                       "+ гистограмму тиров. path = каталог советника/линзы или путь к .jsonl.",
        "input_schema": _obj({"path": "string"}, ["path"]),
        "handler": _governance_verify,
    },
    "calibrate": {
        "description": "Рекомендация подачи (светлый/тёмный) по журналу решений + guardrail захвата. "
                       "Метрика — одобрено-задним-числом, не послушался-ли.",
        "input_schema": _obj({"log_text": "string"}, ["log_text"]),
        "handler": _calibrate,
    },
    "mirror_report": {
        "description": "Зеркало дрейфа: заявленные векторы (во времени) vs одобренные выборы → "
                       "разрыв «говоришь X, выбираешь Y» + дрейф вектора. Не советует, отражает.",
        "input_schema": {"type": "object",
                         "properties": {"stated": {"type": "array"}, "decisions": {"type": "array"}},
                         "required": ["stated", "decisions"]},
        "handler": _mirror_report,
    },
    "premortem": {
        "description": "Пре-мортем исхода: сценарии [{label,value,prob}] → ожидаемый исход + "
                       "крайние случаи. trustworthy=False без истории попаданий (анти-театр).",
        "input_schema": {"type": "object",
                         "properties": {"scenarios": {"type": "array"}, "ledger": {"type": "array"}},
                         "required": ["scenarios"]},
        "handler": _premortem,
    },
    "atomic_grounding": {
        "description": "Атомарная верность: разбить заявление на атомы, сверить каждый гейтом, "
                       "дать inflation gap (насколько единый score завышает обоснованность).",
        "input_schema": _obj({"text": "string", "advisor_dir": "string"}, ["text", "advisor_dir"]),
        "handler": _atomic_grounding,
    },
    "advisor_weights": {
        "description": "Калибровка совета по ИСХОДУ (петля U1): кто был прав ДЛЯ ТЕБЯ → вес голоса. "
                       "records=[{advisor,outcome,endorsed}]. Laplace: без данных вес нейтрален.",
        "input_schema": {"type": "object", "properties": {"records": {"type": "array"}},
                         "required": ["records"]},
        "handler": _advisor_weights,
    },
    "stability": {
        "description": "Доверие через стабильность: вердикты N прогонов → robust/leaning/coin-flip. "
                       "Отличает устойчивый вывод от монетки в обёртке мудрости.",
        "input_schema": {"type": "object", "properties": {"verdicts": {"type": "array"}},
                         "required": ["verdicts"]},
        "handler": _stability,
    },
    "pending_outcomes": {
        "description": "Сёрфейсер петли U1: незакрытые решения (⏳) из журнала — «вернись и закрой». "
                       "Без этого исходы висят вечно и петля не накапливается.",
        "input_schema": _obj({"journal_text": "string"}, ["journal_text"]),
        "handler": _pending_outcomes,
    },
    "loop_status": {
        "description": "Сводка петли исхода: открыто/закрыто + точность прогнозов + доля одобренных. "
                       "ledger=[{decision_id,predicted,actual,endorsed}].",
        "input_schema": {"type": "object", "properties": {"ledger": {"type": "array"}},
                         "required": ["ledger"]},
        "handler": _loop_status,
    },
    "board_status": {
        "description": "Шасси-онбординг: что на доске готово (Принцепс/советники/линзы) + ОДИН "
                       "приоритетный следующий шаг сборки. Зови в начале, чтобы вести юзера за руку.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "handler": _board_status,
    },
    "scaffold_principis": {
        "description": "Собрать principis.md из ответов юзера (who/vector/interface_mode/temperament/"
                       "not_known). Вектор не дан → пробел держим живым. Возвращает markdown — запиши его.",
        "input_schema": {"type": "object", "properties": {"answers": {"type": "object"}},
                         "required": ["answers"]},
        "handler": _scaffold_principis,
    },
    "list_recipes": {
        "description": "Меню «что умеет совет» простыми фразами — покажи юзеру, когда он не знает, "
                       "что спросить, или просит «что ты умеешь / с чего начать». Каждый рецепт: "
                       "title, triggers (фразы), does, reads (как читать результат).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "handler": _list_recipes,
    },
    "validate_manifest": {
        "description": "МОАТ-гейт сборки: проверить тир-манифест советника — region-маркеры реально "
                       "есть в источнике (иначе тиры съедут, 🔵 не на тех словах), тиры валидны, файлы "
                       "на месте. Зови ПЕРЕД build-advisor. advisor_dir = advisors/{имя}.",
        "input_schema": _obj({"advisor_dir": "string"}, ["advisor_dir"]),
        "handler": _validate_manifest,
    },
}


def list_tools():
    """[{name, description, input_schema}] — для tools/list."""
    return [{"name": n, "description": t["description"], "input_schema": t["input_schema"]}
            for n, t in TOOLS.items()]


def dispatch(name, args):
    """Вызвать тул по имени с JSON-аргументами. KeyError на неизвестный тул."""
    return TOOLS[name]["handler"](**args)


# ───────────────────────── транспорт: stdio JSON-RPC (тонкий) ─────────────────────────

def _rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _handle_rpc(msg):
    """JSON-RPC запрос → ответ (или None для нотификаций). Реализует initialize/tools.*"""
    import json
    method, req_id = msg.get("method"), msg.get("id")
    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "consilium-principis", "version": "0.1.0"},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return _rpc_result(req_id, {"tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
            for t in list_tools()]})
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            out = dispatch(params["name"], params.get("arguments") or {})
            return _rpc_result(req_id, {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]})
        except KeyError as e:
            return _rpc_error(req_id, -32601, f"неизвестный тул: {e}")
        except Exception as e:
            return _rpc_error(req_id, -32603, f"ошибка тула: {e}")
    if req_id is not None:
        return _rpc_error(req_id, -32601, f"метод не поддержан: {method}")
    return None


def _serve_stdio():
    """Минимальный построчный JSON-RPC по stdio. Замена — официальный MCP SDK на тот же dispatch."""
    import json
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = _handle_rpc(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    _serve_stdio()
