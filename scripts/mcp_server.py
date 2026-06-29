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

def _root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve(p):
    """Относительный путь → от КОРНЯ репо (а не cwd). Критично: при бридже в Cowork
    Claude Desktop спавнит сервер с НЕОПРЕДЕЛЁННЫМ cwd → 'advisors/x' иначе не найдётся,
    контур молча уйдёт в 🟡. См. CONNECT-MCP.md / правило «пути от __file__»."""
    return p if not p or os.path.isabs(p) else os.path.join(_root(), p)


def _fidelity_check(quote, advisor_dir):
    """Протокол-гейт: наиболее авторитетный тир дословного матча → маркер."""
    m = best_match(quote, _resolve(advisor_dir))
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
    return _eval.retrieve(query, _resolve(advisor_dir), top_k=top_k)


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
    path = _resolve(path)
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
    return inflation_gap(text, _resolve(advisor_dir))


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


def _list_recipes(surface="data"):
    from recipes import load_recipes
    rs = load_recipes()
    if surface == "widget":      # кликабельное меню для mcp__visualize__show_widget (Cowork)
        from recipes import render_widget
        return {"surface": "widget", "content": render_widget(rs)}
    if surface == "html":
        from recipes import render_html
        return {"surface": "html", "content": render_html(rs)}
    return {"recipes": rs}       # сырые данные (дефолт) — хост рендерит сам


def _render_session(session, surface="md", depth="plain", kind="session"):
    """Ход заседания → строка под surface. Контур/гейт 🔵 проходят ДО рендера; тут чистая презентация.
    kind: session (любой ход — реакции+вопросы ИЛИ синтез, авто по наличию synthesis) | opening
    (занавес: роспись советников + приглашение + уточняющие вопросы; объект {advisors:[{name,domain?,
    grounded?}], invitation?, questions?, chips?}). widget = show_widget (Cowork), md/html — портативны.
    depth: plain (дефолт) | expert. Любой ход совета в Cowork рендерь виджетом, не прозой."""
    import session_render as SR
    if surface == "widget":
        content = SR.render_opening(session) if kind == "opening" else SR.render_widget(session, depth=depth)
        return {"surface": "widget", "content": content,
                "next_action": ("ОТОБРАЗИ СЕЙЧАС: вызови mcp__visualize__show_widget с этим `content`. "
                                "НЕ пересказывай этот ход совета прозой — виджет И ЕСТЬ ответ.")}
    fn = {"html": SR.render_html, "md": SR.render_md}.get(surface)
    if fn is None:
        return {"error": f"неизвестный surface: {surface} (md|widget|html)"}
    return {"surface": surface, "content": fn(session)}


def _validate_manifest(advisor_dir):
    from manifest_builder import validate_manifest
    import json as _json
    sd = os.path.join(_resolve(advisor_dir), "sources")
    mp = os.path.join(sd, "manifest.json")
    if not os.path.isfile(mp):
        return {"ok": True, "problems": [], "note": "нет манифеста → всё P1 (бэк-компат)"}
    return validate_manifest(_json.load(open(mp, encoding="utf-8")), sd)


# ── lifecycle: весь цикл сборки через MCP, чтобы юзер не выходил из своего агента ──
# (раньше жили только в board.py CLI → в чистом MCP-хосте без шелла были недоступны)

# Долгие тулы (seed/build/ingest) рвут таймаут MCP-транспорта (живой прогон в Cowork это
# подтвердил). Фикс: фоновый ДЖОБ — тул стартует поток, сразу отдаёт job_id, хост опрашивает
# job_status. Реестр в памяти процесса (живёт, пока жив сервер); потоки daemon.
import threading

_JOBS = {}
_JOBS_LOCK = threading.Lock()
_JOB_SEQ = [0]


def _start_job(fn, label):
    with _JOBS_LOCK:
        _JOB_SEQ[0] += 1
        jid = "job-%d" % _JOB_SEQ[0]
        _JOBS[jid] = {"status": "running", "label": label, "result": None, "error": None}

    def _run():
        try:
            r = fn()
            with _JOBS_LOCK:
                _JOBS[jid].update(status="done", result=r)
        except Exception as e:
            with _JOBS_LOCK:
                _JOBS[jid].update(status="error", error=str(e))
    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": jid, "status": "running", "label": label,
            "note": "долгая операция в фоне — опрашивай job_status(job_id), не жди в этом вызове"}


def _job_status(job_id):
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else {"error": "нет такого job_id: %s" % job_id}


def _doctor():
    from doctor import run_doctor
    return run_doctor(_root())


# do-функции синхронны (их и зовёт board.py CLI без таймаута); тул-обёртки — фоновые джобы.
def _do_build(advisor_dir, author=None, run_kernels=True, run_index=True):
    from build_orchestrator import build_advisor_full
    return build_advisor_full(_resolve(advisor_dir), author=author,
                              run_kernels=run_kernels, run_index=run_index)


def _do_seed():
    from seed import run_seed_council
    return {"results": run_seed_council(_root())}


def _do_ingest(handle, out_path=None):
    from ingest_telegram import ingest
    return ingest(handle, _resolve(out_path) if out_path
                  else os.path.join(_root(), "principis_corpus", "telegram.jsonl"))


def _build_advisor(advisor_dir, author=None, run_kernels=True, run_index=True):
    """Советник под ключ (МАНИФЕСТ-ГЕЙТ→corpus→kernels→индекс) — ФОНОВЫЙ ДЖОБ (долго)."""
    return _start_job(lambda: _do_build(advisor_dir, author, run_kernels, run_index),
                      "build_advisor:%s" % advisor_dir)


def _seed_council():
    """Стартовый совет PD-мудрецов с нуля — ФОНОВЫЙ ДЖОБ (долго + сеть Gutenberg)."""
    return _start_job(_do_seed, "seed_council")


def _ingest_telegram(handle, out_path=None):
    """Канал → корпус Принцепса — ФОНОВЫЙ ДЖОБ (сеть)."""
    return _start_job(lambda: _do_ingest(handle, out_path), "ingest_telegram:%s" % handle)


def _setup_full(consent=True):
    """Поднять FULL-тир: системный ollama НИКОГДА не ставим молча (вернём инструкцию),
    pull модели bge-m3 — авто при consent. Возвращает шаги + финальный probe()."""
    from setup_full import run_setup
    return run_setup(consent=consent)


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
                       "что спросить, или просит «что ты умеешь / с чего начать». surface: data "
                       "(сырые рецепты, дефолт) | widget (кликабельный HTML для show_widget в Cowork) "
                       "| html (самодостаточный фолбэк).",
        "input_schema": {"type": "object",
                         "properties": {"surface": {"type": "string"}}, "required": []},
        "handler": _list_recipes,
    },
    "render_session": {
        "description": "ОБЯЗАТЕЛЬНЫЙ финал заседания совета в Cowork: отрисовать canon-объект "
                       "заседания виджетом. Зови этот тул ПОСЛЕДНИМ действием, потом скорми "
                       "вернувшийся `content` в mcp__visualize__show_widget — вердикт прозой НЕ пиши. "
                       "surface: widget (Cowork, дефолт-выбор, кликабельный sendPrompt) | md "
                       "(только если show_widget недоступен) | html (фолбэк). Контур/гейт 🔵 "
                       "пройдены ризонингом ДО рендера. depth=plain по умолчанию. См. session_render.py.",
        "input_schema": {"type": "object",
                         "properties": {"session": {"type": "object"}, "surface": {"type": "string"},
                                        "depth": {"type": "string", "enum": ["plain", "expert"]},
                                        "kind": {"type": "string", "enum": ["session", "opening"]}},
                         "required": ["session"]},
        "handler": _render_session,
    },
    "validate_manifest": {
        "description": "МОАТ-гейт сборки: проверить тир-манифест советника — region-маркеры реально "
                       "есть в источнике (иначе тиры съедут, 🔵 не на тех словах), тиры валидны, файлы "
                       "на месте. Зови ПЕРЕД build-advisor. advisor_dir = advisors/{имя}.",
        "input_schema": _obj({"advisor_dir": "string"}, ["advisor_dir"]),
        "handler": _validate_manifest,
    },
    "doctor": {
        "description": "Health-check машины БЕЗ выхода из агента: Python, скилл установлен, какой тир "
                       "(ollama?), самотест рва (P1→🔵, фейк→None). Read-only. Зови, чтобы понять, "
                       "готова ли эта машина собирать.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "handler": _doctor,
    },
    "build_advisor": {
        "description": "Собрать советника под ключ ИЗ АГЕНТА: манифест-гейт → corpus → kernels → индекс. "
                       "advisor_dir = advisors/{имя}. ФОНОВЫЙ ДЖОБ (долго): вернёт {job_id} сразу — "
                       "опрашивай job_status(job_id), не жди здесь. Сначала validate_manifest.",
        "input_schema": {"type": "object",
                         "properties": {"advisor_dir": {"type": "string"}, "author": {"type": "string"},
                                        "run_kernels": {"type": "boolean"}, "run_index": {"type": "boolean"}},
                         "required": ["advisor_dir"]},
        "handler": _build_advisor,
    },
    "seed_council": {
        "description": "Собрать стартовый совет PD-мудрецов (Аврелий+Эпиктет) с нуля — холодный старт "
                       "без шелла. ФОНОВЫЙ ДЖОБ (долго + сеть Gutenberg): вернёт {job_id} сразу, "
                       "опрашивай job_status. Идемпотентно по уже собранным.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "handler": _seed_council,
    },
    "ingest_telegram": {
        "description": "Публичный Telegram-канал → корпус Принцепса (твои слова = P1). ФОНОВЫЙ ДЖОБ "
                       "(сеть): вернёт {job_id}, опрашивай job_status. handle = @name или name. "
                       "0 постов = приватный/неверный/sandbox-блок сети.",
        "input_schema": {"type": "object",
                         "properties": {"handle": {"type": "string"}, "out_path": {"type": "string"}},
                         "required": ["handle"]},
        "handler": _ingest_telegram,
    },
    "job_status": {
        "description": "Статус фонового джоба по job_id (от build_advisor/seed_council/ingest_telegram): "
                       "status = running | done (с result) | error (с error). Опрашивай, пока не done.",
        "input_schema": {"type": "object",
                         "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
        "handler": _job_status,
    },
    "setup_full": {
        "description": "Поднять FULL-тир (семантика) ИЗ АГЕНТА: системный ollama НЕ ставим молча "
                       "(вернём инструкцию под ОС), модель bge-m3 — авто-pull при consent. Возвращает "
                       "шаги + финальный статус. consent=false → только план, без выполнения.",
        "input_schema": {"type": "object",
                         "properties": {"consent": {"type": "boolean"}}, "required": []},
        "handler": _setup_full,
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


# Server-level instructions: ЕДИНСТВЕННЫЙ канал, которым правила доходят до MCP-хоста (Cowork/
# Desktop). Хост НЕ читает SKILL.md — он видит только тулы + это. Держать кратко и императивно.
INSTRUCTIONS = """\
Consilium-Principis — личный совет AI-персон реальных мыслителей, заземлённый на их тексты, с
защитным контуром верности. Ты (хост) арендуешь ризонинг; сервер даёт контекст + гейт. Правила:

1. КОНТУР ВЕРНОСТИ (протокол-гейт, НЕ нарушай). Маркер 🔵 (дословная цитата) ставь ТОЛЬКО если
   `fidelity_check` подтвердил (status 🔵). Иначе — 🟡 (экстраполяция). НИКОГДА не выдумывай цитаты
   и не приписывай 🔵 без подтверждения. Совет с пустым корпусом не цитирует — воздержись.
   ЧТОБЫ БЫЛИ 🔵-ЦИТАТЫ: бери в quote.text ТОЧНЫЙ текст пассажа из `retrieve` (дословно, как
   вернулось), и `fidelity_check` подтвердит 🔵. НЕ перефразируй и НЕ переводи текст цитаты до
   гейта — пересказ → 🟡. (Перевод-глоссу клади в quote.translation, оригинал в quote.text.)

0. ТИХАЯ ОРКЕСТРАЦИЯ. Вызовы retrieve/fidelity_check/render_session/ошибки-ретраи делай МОЛЧА —
   НЕ описывай их в чате («тяну пассажи», «проверяю дословность», «пересобираю»). Пользователь
   видит только короткую подводку (1-2 строки) + сам виджет. Техническая кухня — за кулисами.

5. ЖИВОЙ КРУГЛЫЙ СТОЛ, А НЕ ОРАКУЛ (по умолчанию для открытых/важных вопросов). НЕ прыгай сразу
   к вердикту-виджету. Сначала советники РЕАГИРУЮТ в своих голосах и, если вопросу не хватает
   контекста/ставка высока, ЗАДАЮТ юзеру 1-3 уточняющих вопроса («прежде чем советовать — ответь:
   …», заполняя пробелы), и/или ведут короткий живой обмен между собой (спорят, реагируют, named
   «Макиавелли → Аврелий»). Юзер отвечает и вклинивается свободно. Это происходит В ЧАТЕ голосами
   советников (не «техническая кухня» — это и есть ценность). Синтез-ВИДЖЕТ (правило 2) рендеришь
   КОГДА контекст собран или юзер просит «давай синтез». Для уже чёткого вопроса можно сразу к
   виджету. Главная ценность совета — допрос и challenge ДО ответа, а не быстрый оракул.

6. ЛЮБОЙ ХОД СОВЕТА = ВИДЖЕТ (оформление везде, не только финал). Каждая реплика совета юзеру
   рендерится виджетом через render_session→show_widget, прозой — никогда: (а) ОПЕНИНГ (занавес) —
   `render_session(obj, surface=widget, kind=opening)`, obj={advisors:[{name, domain, grounded}],
   invitation, questions?, chips?}; (б) ХОД КРУГЛОГО СТОЛА (реакции советников + уточняющие вопросы,
   ещё без вердикта) — обычный canon-объект БЕЗ `synthesis`, но с `questions:[...]` (совет спрашивает);
   (в) СИНТЕЗ — объект С `synthesis`. Один и тот же `render_session(surface=widget)` рендерит все три.

2. РЕНДЕР СИНТЕЗА = ВИДЖЕТ, НЕ ПРОЗА (обязательно). Когда заседание дошло до синтеза (см. правило 5),
   ты ОБЯЗАН отдать его виджетом через `mcp__visualize__show_widget`, а НЕ текстом. Конвейер:
   (а) собери canon-объект `{question, reframe?, advisors:[{name, opinions:[{marker, argument,
   quote?}]}], disagreement?, synthesis, step}`; (б) вызови `render_session(session,
   surface="widget", depth="plain")`; (в) скорми вернувшийся `content` в `show_widget`. Вердикт
   прозой НЕ пиши и НЕ «предлагай отрисовать» — рендер виджетом И ЕСТЬ ответ. В чат — 1-2 строки
   подводки максимум. Markdown (`surface="md"`) — только если `show_widget` недоступен.

3. СОГЛАСИЕ НА КОНТЕКСТ (non-capture). Базовый контекст = корпуса советников + заданный вопрос.
   Контекст СВЕРХ этого (память юзера, другие проекты, внешнее) — спрашивай разрешение, прежде
   чем вплетать (если в Принцепсе не стоит allow). Молча тянуть профиль юзера = захват, нельзя.

4. Подача: отвечай на языке юзера; 🔵-цитата остаётся дословной в оригинале + перевод-глосса.
   depth=plain по умолчанию (без вероятностей/разбора); expert — по запросу.
"""


def _handle_rpc(msg):
    """JSON-RPC запрос → ответ (или None для нотификаций). Реализует initialize/tools.*"""
    import json
    method, req_id = msg.get("method"), msg.get("id")
    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "consilium-principis", "version": "0.1.0"},
            "instructions": INSTRUCTIONS,
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
