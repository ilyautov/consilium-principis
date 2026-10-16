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


def _cli_backend():
    """LLM_BACKEND=claude|codex|kimi → имя подписочного бэкенда (cli_backends), иначе None."""
    import cli_backends
    b = os.getenv("LLM_BACKEND", "ollama").strip().lower()
    return b if b in cli_backends.BACKENDS else None


def generate(prompt, model=None, temperature=0.3, timeout=120, num_predict=None, allow_cloud=True):
    """Prompt → строка-ответ модели. Бэкенд — env LLM_BACKEND: "ollama" (дефолт) | "openrouter" |
    "claude" | "codex" | "kimi" (подписочные CLI, cli_backends — без API-ключа, на логине CLI).
    Fail-closed цепочка: openrouter/подписка упала/нет ключа/нет CLI → ollama; ollama упал →
    исключение наружу (вызыватели-судьи трактуют исключение как gated/withheld). Подписка — тоже
    облако (вопрос уходит провайдеру), поэтому подчиняется тому же allow_cloud, что и openrouter.
    temperature/num_predict подписочные CLI не принимают — игнорируются (судья всё равно парсит
    первую цифру ответа). Детерминизм в тестах — моки raw-функций и cli_backends._run.

    num_predict (опц.): потолок токенов ответа, пробрасывается в оба raw-вызова.
    allow_cloud (H4): False → облачный (openrouter) бэкенд НЕ трогается даже при LLM_BACKEND=openrouter.
    Судья релевантности зовёт с False ПО УМОЛЧАНИЮ (независимость гейта и воспроизводимость MOAT/eval не
    зависят от внешнего API); True — только прод-путь relevance_gate при judge_backend="api" (opt-in юзера).

    Проброс num_predict — условный (kwarg только когда задан): держит старые моки raw-функций
    с сигнатурой (p, m, t, to) рабочими без правок."""
    extra = {} if num_predict is None else {"num_predict": num_predict}
    cli = _cli_backend() if allow_cloud else None
    if cli:
        import cli_backends
        if cli not in cli_backends.JUDGE_SAFE and os.getenv("CONSILIUM_ALLOW_KIMI_JUDGE") != "1":
            # Kimi в судьях — только по явному opt-in: у него нет жёсткого выключателя тулов, а
            # судья кормится сырым текстом корпуса (инъекции). Деградируем как при сбое подписки.
            return _raw_generate(prompt, GEN_MODEL, temperature, timeout, **extra)
        try:
            return cli_backends.generate(prompt, cli, model=model,
                                         timeout=max(timeout, 60))
        except cli_backends.CLIBackendError:
            pass  # fail-closed: падаем на локальный ollama ниже
        # model здесь — имя модели ПОДПИСКИ (opus/gpt-5…), ollama его не знает → её дефолт
        return _raw_generate(prompt, GEN_MODEL, temperature, timeout, **extra)
    if allow_cloud and os.getenv("LLM_BACKEND", "ollama") == "openrouter":
        api_model = model or os.getenv("LLM_API_MODEL")
        if api_available() and api_model:
            try:
                return _raw_generate_openrouter(prompt, api_model, temperature, timeout, **extra)
            except Exception:
                pass  # fail-closed: падаем на локальный ollama ниже
    return _raw_generate(prompt, model or GEN_MODEL, temperature, timeout, **extra)


def api_available():
    """Облачный бэкенд имеет смысл пробовать? Без сетевого пробинга: OPENROUTER_API_KEY задан ИЛИ
    LLM_BACKEND указывает на установленный подписочный CLI (claude|codex|kimi). Живость подписки
    (квота/логин) тут не проверяется — generate честно деградирует к ollama, судья — к host."""
    if os.getenv("OPENROUTER_API_KEY"):
        return True
    cli = _cli_backend()
    if cli:
        import cli_backends
        if cli not in cli_backends.JUDGE_SAFE and os.getenv("CONSILIUM_ALLOW_KIMI_JUDGE") != "1":
            return False   # generate всё равно уйдёт в ollama — не врём судье/лейблу «подписка kimi»
        return cli_backends.available(cli)
    return False


def available(timeout=5):
    """ollama жив? Gate для РЕАЛЬНЫХ прогонов (судья/генератор), чтобы не выдавать вырождение за истину."""
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False
