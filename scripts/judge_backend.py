#!/usr/bin/env python3
"""§2.2 moat-v2: уровни независимости судьи релевантности + честный лейбл.

Массовый юзер = Claude-only (без ollama, без API-ключа) на lexical-тире, где серверный
судья (relevance_judge через ollama/OpenRouter) не существует → у самого массового пути
НОЛЬ защиты релевантности. Ответ — иерархия бэкендов судейства:

  api    — независимый облачный (OpenRouter; ключ ТОЛЬКО из env, никогда в репо;
           данные уходят провайдеру — это пишется в лейбл честно);
  ollama — независимый локальный;
  host   — self-check: судит сам ХОСТ (заинтересованная сторона — его оценки гейтят
           его же цитаты), поэтому РЕШЕНИЕ (порог/маркеры/лимит) остаётся в коде,
           а оценки логируются (аудит-трейл). Двухфазный протокол — mcp_server.

Резолюция (конфиг board_config.json → relevance_gate.judge_backend, дефолт auto):
  auto   : host (2026-07-24). Судит сам хост двухфазным протоколом — работает на ЛЮБОЙ
           машине (без ollama, без чат-модели), а когда хост = сильная модель (Claude),
           релевантность судится ТОЧНЕЕ и на порядок быстрее локального ollama-судьи
           (gemma3:27b ~5с/пассаж рвал 60с MCP-таймаут при веере совета; host — 0.2с).
           Вербатим-🔵 всё равно детерминирован в коде → host двигает лишь флаг РЕЛЕВАНТНОСТИ,
           не ядро рва. НИКОГДА не в облако (и даже локальный ollama — только по явному выбору).
           Прежний auto→ollama (до 2026-07-24) тихо ломал судью на FULL-тире БЕЗ большой чат-модели
           (а мы просим тянуть только bge-m3) и был медленным на мощной машине.
  явный  : независимый судья = OPT-IN «больше приколюх при наличии железа». judge_backend="ollama"
           (локальный) / "api" (облачный, ЯВНОЕ согласие на egress). Fail-closed деградация ВНИЗ:
           api → ollama → host. host — пол иерархии (его fail-closed = 🟡).
  env    : CONSILIUM_JUDGE_BACKEND=host|ollama|api — ЖЁСТКИЙ пин без пробинга
           (dev/тесты; api-пин = явное согласие; тест-сьют пинит ollama, чтобы
           легаси-контракт single-phase оставался покрыт — см. tests/conftest.py).

Семантика для протокола: host → двухфазное судейство (cite отдаёт judgment_request,
хост зовёт gate_verdict); ollama/api → single-phase, сервер судит сам, поведение
байт-в-байт прежнее. Для api сам вызов идёт через llm_local.generate (env
LLM_BACKEND=openrouter + LLM_API_MODEL) — своя fail-closed цепочка там же.
"""
import os

VALID_BACKENDS = ("host", "ollama", "api")
ENV_PIN = "CONSILIUM_JUDGE_BACKEND"

_INDEPENDENCE = {"host": "self-check",
                 "ollama": "independent-local",
                 "api": "independent-cloud"}

_LABELS = {
    "host": "self-check: судит сам хост (заинтересованная сторона), решение в коде",
    "ollama": "независимый (локальный)",
    "api": "независимый (облако — данные уходят провайдеру)",
}


def configured(advisor_dir=None):
    """Сконфигурированный уровень из board_config.json (relevance_gate.judge_backend).
    Мусор/отсутствие → "auto" (коэрс fail-closed в relevance_gate._gate_config)."""
    import relevance_gate
    return relevance_gate._gate_config(advisor_dir).get("judge_backend", "auto")


def resolve(advisor_dir=None) -> str:
    """Фактический бэкенд судьи релевантности: "host" | "ollama" | "api".

    ДЕФОЛТ (auto, 2026-07-24) = host: судит сам вызывающий хост (в MCP — сама модель) через
    двухфазный протокол (cite→judgment_request→gate_verdict). Работает БЕЗ ollama и БЕЗ чат-модели
    → едет на ЛЮБОЙ машине одинаково: массовый Claude-only тир И FULL-тир-без-чат-модели (мы просим
    тянуть только bge-m3 для эмбеддинга — большой чат-модели у юзера обычно НЕТ, и старый auto→ollama
    тихо ломал ему судью). Когда хост сильный (Claude), релевантность судится ТОЧНЕЕ локального
    ollama-судьи и на порядок быстрее (0.2с против ~5с/пассаж на gemma3:27b). Вербатим-🔵 остаётся
    ДЕТЕРМИНИРОВАННЫМ кодом при любом бэкенде → host-дефолт двигает лишь флаг РЕЛЕВАНТНОСТИ, не ядро рва.

    Независимый судья — ЯВНЫЙ opt-in (config relevance_gate.judge_backend или env-пин), «больше
    приколюх при наличии железа»:
      ollama — независимый локальный (нужен запущенный ollama + чат-модель);
      api    — независимый облачный (privacy: вопрос уходит провайдеру → ТОЛЬКО по явному выбору,
               НИКОГДА из auto).
    Явный выбор честно деградирует к host, если бэкенд недоступен (не молчим, не клауди из auto).
    Env-пин CONSILIUM_JUDGE_BACKEND — жёсткий (без пробинга): dev/тесты."""
    pin = os.getenv(ENV_PIN, "").strip().lower()
    if pin in VALID_BACKENDS:
        return pin                                     # env-пин = явное согласие (включая api)
    import llm_local
    choice = configured(advisor_dir)
    if choice == "ollama":                             # явный opt-in: независимый локальный судья
        return "ollama" if llm_local.available() else "host"
    if choice == "api":                                # явный opt-in на облако (privacy-согласие)
        if llm_local.api_available():
            return "api"
        return "ollama" if llm_local.available() else "host"   # api-без-ключа → цепочка к host
    return "host"                                      # auto (дефолт) и любой прочий → host


def info(advisor_dir=None) -> dict:
    """{"backend", "independence", "label"} — честный лейбл уровня для doctor/статуса."""
    b = resolve(advisor_dir)
    return {"backend": b, "independence": _INDEPENDENCE[b], "label": _LABELS[b]}
