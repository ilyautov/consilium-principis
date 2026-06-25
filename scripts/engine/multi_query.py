"""Левер 2: multi-query / STORM — сетка перефразировок из ЛИНЗ советника.

Генератор (qwen2.5 через ollama) видит ТОЛЬКО (вопрос + линзы советника), вслепую к корпусу и
anchor'ам. Линза = заранее объявленная рамка советника (persona.md), поэтому для Макиавелли
линза «лев-и-лиса» легитимно рождает запрос про лису/льва — мост к пассажу, до которого один
абстрактный запрос не дотягивался. Выдачи вариантов сливаются тем же RRF (engine/rrf.py).

В проде генератор — LLM-слой скилла (Claude). Здесь, офлайн, — локальный qwen2.5 как стенд-ин
того же механизма (и для воспроизводимого замера лифта).
"""
import os
import json
import urllib.request

from .rrf import rrf_fuse

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GEN_MODEL = os.getenv("MULTIQUERY_MODEL", "qwen2.5:7b")


def generate_variants(question, lenses, n=5, lang="English", model=None, timeout=90):
    """N перефразировок вопроса через линзы советника, в языке корпуса. Вслепую к anchor."""
    lens_str = ", ".join(lenses) if lenses else "(no specific lenses)"
    prompt = (
        "You reformulate a user's question to improve retrieval from one thinker's OWN writings.\n"
        f"The thinker habitually reasons through these recurring lenses: {lens_str}.\n"
        f"Rewrite the question into {n} diverse search queries, each viewing it through a DIFFERENT "
        "lens, using concrete vocabulary likely to appear in the source text (its metaphors, key terms).\n"
        f"STRICT: write ENTIRELY in {lang}. Translate every lens/concept into {lang} "
        "(e.g. a Russian lens name must be rendered as its English meaning, never copied verbatim). "
        "No foreign words, no transliteration. Do NOT answer the question. One query per line, no numbering.\n\n"
        f"Question: {question}\n\nQueries:"
    )
    body = json.dumps({"model": model or GEN_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.4}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read()).get("response", "")
    variants = [ln.strip(" -•\t0123456789.)").strip() for ln in out.splitlines() if ln.strip()]
    import re
    # фикс B: выкинуть варианты с протёкшей кириллицей (code-mixed мусор ретрив хоронит)
    variants = [v for v in variants if len(v) > 8 and not re.search(r"[а-яА-ЯёЁ]", v)]
    return variants[:n]


def multiquery_retrieve(engine, advisor_dir, variants, top_k=3):
    """Слить выдачи всех вариантов через RRF. Варианты уже в языке корпуса → query_lex=сам вариант."""
    lists = []
    pool = max(top_k, 20)
    for v in variants:
        try:
            hits = engine.retrieve(v, advisor_dir, top_k=pool, query_lex=v)  # Hybrid
        except TypeError:
            hits = engine.retrieve(v, advisor_dir, top_k=pool)               # Semantic/Lexical
        lists.append(hits)
    return rrf_fuse(lists, top_k=top_k)
