"""Тонкий фасад локальной LLM (ollama /api/generate) — ЕДИНАЯ точка вызова для eval-rigor
(судья релевантности / генератор синтетики / рекурсивный луп). Раньше вызов /api/generate был
скопирован в gen_golden/exp_bridge/kernel_extract/multi_query; здесь он один и МОКАЕТСЯ в тестах
через monkeypatch `llm_local._raw_generate` → тесты не трогают сеть/ollama (CI-инвариант)."""
import os
import json
import urllib.request

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GEN_MODEL = os.getenv("KERNEL_MODEL", "gemma3:27b")


def _raw_generate(prompt, model, temperature, timeout, num_predict=None):
    """Сырой вызов ollama. Единственная точка, которую монкипатчат тесты (без сети).
    num_predict (опц.) → options.num_predict: жёсткий потолок токенов ответа (судья ждёт
    одну цифру — незачем генерить сотни токенов)."""
    opts = {"temperature": temperature}
    if num_predict is not None:
        opts["num_predict"] = num_predict
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": opts}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("response", "")


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _raw_generate_openrouter(prompt, model, temperature, timeout, num_predict=None):
    """Сырой вызов OpenRouter (chat/completions). Мокается в тестах — без сети.
    num_predict (опц.) → max_tokens: потолок токенов ответа."""
    payload = {"model": model,
               "messages": [{"role": "user", "content": prompt}],
               "temperature": temperature}
    if num_predict is not None:
        payload["max_tokens"] = num_predict
    body = json.dumps(payload).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def generate(prompt, model=None, temperature=0.3, timeout=120, num_predict=None, allow_cloud=True):
    """Prompt → строка-ответ модели. Бэкенд — env LLM_BACKEND: "ollama" (дефолт) | "openrouter".
    Fail-closed цепочка: openrouter упал/нет ключа → ollama; ollama упал → исключение наружу
    (вызыватели-судьи трактуют исключение как gated/withheld). Детерминизм в тестах — моки raw-функций.

    num_predict (опц.): потолок токенов ответа, пробрасывается в оба raw-вызова.
    allow_cloud (H4): False → облачный (openrouter) бэкенд НЕ трогается даже при LLM_BACKEND=openrouter.
    Судья релевантности зовёт с False ПО УМОЛЧАНИЮ (независимость гейта и воспроизводимость MOAT/eval не
    зависят от внешнего API); True — только прод-путь relevance_gate при judge_backend="api" (opt-in юзера).

    Проброс num_predict — условный (kwarg только когда задан): держит старые моки raw-функций
    с сигнатурой (p, m, t, to) рабочими без правок."""
    extra = {} if num_predict is None else {"num_predict": num_predict}
    if allow_cloud and os.getenv("LLM_BACKEND", "ollama") == "openrouter":
        api_model = model or os.getenv("LLM_API_MODEL")
        if api_available() and api_model:
            try:
                return _raw_generate_openrouter(prompt, api_model, temperature, timeout, **extra)
            except Exception:
                pass  # fail-closed: падаем на локальный ollama ниже
    return _raw_generate(prompt, model or GEN_MODEL, temperature, timeout, **extra)


def api_available():
    """OPENROUTER_API_KEY задан? Без сетевого пробинга: ключ есть → API-бэкенд имеет смысл пробовать."""
    return bool(os.getenv("OPENROUTER_API_KEY"))


def available(timeout=5):
    """ollama жив? Gate для РЕАЛЬНЫХ прогонов (судья/генератор), чтобы не выдавать вырождение за истину."""
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False
