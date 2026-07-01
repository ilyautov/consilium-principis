"""Тонкий фасад локальной LLM (ollama /api/generate) — ЕДИНАЯ точка вызова для eval-rigor
(судья релевантности / генератор синтетики / рекурсивный луп). Раньше вызов /api/generate был
скопирован в gen_golden/exp_bridge/kernel_extract/multi_query; здесь он один и МОКАЕТСЯ в тестах
через monkeypatch `llm_local._raw_generate` → тесты не трогают сеть/ollama (CI-инвариант)."""
import os
import json
import urllib.request

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GEN_MODEL = os.getenv("KERNEL_MODEL", "gemma3:27b")


def _raw_generate(prompt, model, temperature, timeout):
    """Сырой вызов ollama. Единственная точка, которую монкипатчат тесты (без сети)."""
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": temperature}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("response", "")


def generate(prompt, model=None, temperature=0.3, timeout=120):
    """Prompt → строка-ответ локальной модели. Детерминизм в тестах — через мок `_raw_generate`."""
    return _raw_generate(prompt, model or GEN_MODEL, temperature, timeout)


def available(timeout=5):
    """ollama жив? Gate для РЕАЛЬНЫХ прогонов (судья/генератор), чтобы не выдавать вырождение за истину."""
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False
