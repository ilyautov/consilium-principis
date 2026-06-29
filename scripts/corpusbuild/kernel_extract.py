"""Экстракция кернелов (мета-идей) автора через LLM — СТАБИЛЬНЫЙ продакшн-модуль.

Раньше corpusbuild/kernels.py тянул эту функцию из exp_kernels.py (experiment-файл) — хрупко:
«чистка экспериментов» сломала бы сборку кернелов и build_lens. Ядро вынесено сюда; exp_kernels
переиспользует его же (один источник истины). Метод фальсиф-валиден (см. exp_kernels: held-out
дискриминация own>alt значима для Aurelius/Machiavelli)."""
import os
import re
import json
import urllib.request

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
KERNEL_MODEL = os.getenv("KERNEL_MODEL", "gemma3:27b")


def extract_kernels(author, train, k=6, n_sample=28):
    """train=[{"text":…}…] (P1-пассажи) → до k строк «имя — порождающий метод» (gemma).
    Сэмплируем равномерно, просим МЕТОДЫ рассуждения (не темы), применимые к новым задачам."""
    step = max(1, len(train) // n_sample)
    sample = [train[i]["text"][:320].strip() for i in range(0, len(train), step)][:n_sample]
    passages = "\n---\n".join(sample)
    prompt = (
        f"You are analyzing the writings of {author}. Below are passages sampled from the corpus.\n"
        f"Identify the {k} META-IDEAS (generative kernels) that GENERATE these and the author's other "
        "writings — the recurring THINKING METHODS and core principles running through everything, NOT "
        "surface topics. For each: a short name and ONE sentence capturing the generative move (HOW the "
        "author reasons), phrased so it could apply to NEW problems the author never wrote about.\n"
        f"Output exactly {k} lines, each:\nKERNEL: <name> — <one-sentence generative method>\n\n"
        f"Passages:\n{passages}\n"
    )
    body = json.dumps({"model": KERNEL_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.4}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=420) as r:
        out = json.loads(r.read()).get("response", "")
    kernels = []
    for ln in out.splitlines():
        m = re.match(r"\s*KERNEL[:\-]\s*(.+)", ln, re.I)
        if m:
            kernels.append(m.group(1).strip())
    return kernels
