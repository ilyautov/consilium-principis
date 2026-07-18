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
  auto   : ollama жив → ollama; иначе host. НИКОГДА не уходит в облако молча,
           даже если api-ключ есть в env. Приватность вопроса юзера важнее
           независимости судьи: облако = данные уходят провайдеру, а это выбор,
           а не умолчание (был обратный дефолт до 2026-07-18; см. ниже).
  явный  : выбранный уровень, с fail-closed деградацией ВНИЗ по независимости
           api → ollama → host. host — пол иерархии: его собственный fail-closed
           (нет вердикта / кривой nonce) = 🟡, т.е. цепочка спеки «выбранный →
           ollama → 🟡» заканчивается в host-протоколе, который сам кончается 🟡.
           judge_backend="api" в конфиге = ЯВНОЕ согласие на облако (opt-in).
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
    """Фактический бэкенд судьи: "host" | "ollama" | "api" (см. модульный докстринг).
    Пробинг дешёвый (api = наличие ключа; ollama = HTTP на localhost, refused мгновенен);
    env-пин пробинг обходит целиком → в тестах сети нет."""
    pin = os.getenv(ENV_PIN, "").strip().lower()
    if pin in VALID_BACKENDS:
        return pin                                     # env-пин = явное согласие (включая api)
    import llm_local
    choice = configured(advisor_dir)
    if choice == "host":
        return "host"
    # Облако (api) — ТОЛЬКО по явному выбору (config judge_backend="api" или env-пин).
    # auto НИКОГДА не уходит в облако молча, даже при наличии ключа: приватность вопроса
    # юзера > независимости судьи. api остаётся в одну строку конфига (opt-in).
    if choice == "api" and llm_local.api_available():
        return "api"
    if llm_local.available():                          # auto / api-без-ключа / ollama деградируют сюда
        return "ollama"
    return "host"                                      # пол: self-check с решением в коде


def info(advisor_dir=None) -> dict:
    """{"backend", "independence", "label"} — честный лейбл уровня для doctor/статуса."""
    b = resolve(advisor_dir)
    return {"backend": b, "independence": _INDEPENDENCE[b], "label": _LABELS[b]}
