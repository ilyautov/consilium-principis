#!/usr/bin/env python3
"""Э0: генератор eval-golden из корпуса (provenance target_tier=P1).

Стратифицированно сэмплит чанки по всему корпусу → LLM генерит ДВА вопроса на чанк:
  • literal  — прямой вопрос в терминах пассажа;
  • abstract — концептуальный, без характерных слов пассажа (стресс для ретрива).
anchor = характерное предложение чанка (hit-проверка как в eval: anchor ⊂ извлечённый текст).

Ловушки (см. provenance-схему): лёгкость синтетики (abstract-вариант + difficulty-метка),
self-bias (генерим LLM, ретрив — bge-m3, разные системы), валидация (печатать сэмпл руками).
Модель: env GOLDEN_MODEL (дефолт qwen2.5:7b — скорость; gemma3:27b — качество).
"""
import sys, os, json, re, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild.paths import corpus_path
from golden_meta import meta_record

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GOLDEN_MODEL = os.getenv("GOLDEN_MODEL", "qwen2.5:7b")
AUTHORS = {"machiavelli": "Niccolò Machiavelli", "marcus-aurelius": "Marcus Aurelius"}


def load_chunks(adv):
    return [json.loads(l) for l in open(corpus_path(adv), encoding="utf-8") if l.strip()]


def stratified(chunks, k):
    """Равномерно по корпусу, пропуская служебные/короткие (заголовки, фронт-маттер)."""
    good = [c for c in chunks if len(c.get("text", "")) > 350 and "# SOURCE:" not in c["text"][:40]]
    if len(good) <= k:
        return good
    step = len(good) / k
    return [good[int(i * step)] for i in range(k)]


def anchor_of(text):
    """Самое длинное предложение (30..200 симв) = характерный якорь, целиком внутри чанка."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 30 <= len(s.strip()) <= 200]
    return max(sents, key=len) if sents else None


def gen_questions(author, passage, model, timeout=120):
    prompt = (
        f"Below is a passage from {author}'s own writing.\n"
        "Generate TWO search questions that THIS SPECIFIC passage answers:\n"
        "1. LITERAL — a direct question using the passage's own concepts.\n"
        "2. ABSTRACT — a conceptual question someone would ask WITHOUT having read it, "
        "avoiding the passage's distinctive words/phrases.\n"
        "Each must be answered specifically by THIS passage, not generic. Do NOT quote the passage.\n"
        "Output exactly two lines:\nLITERAL: <question>\nABSTRACT: <question>\n\n"
        f"Passage:\n{passage}\n"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.3}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read()).get("response", "")
    lit = ab = None
    for ln in out.splitlines():
        m = re.match(r"\s*LITERAL[:\-]\s*(.+)", ln, re.I)
        if m:
            lit = m.group(1).strip()
        m = re.match(r"\s*ABSTRACT[:\-]\s*(.+)", ln, re.I)
        if m:
            ab = m.group(1).strip()
    return lit, ab


def run(slug, k, model):
    adv = f"advisors/{slug}"
    author = AUTHORS.get(slug, slug)
    chunks = stratified(load_chunks(adv), k)
    out_path = f"scripts/golden/{slug}.auto.jsonl"
    n = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        meta = meta_record(adv)                       # §1.4: хэш корпуса на момент генерации
        if meta:
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for c in chunks:
            anc = anchor_of(c["text"])
            if not anc:
                continue
            try:
                lit, ab = gen_questions(author, c["text"][:1400], model)
            except Exception as e:
                print(f"  [skip] {e}")
                continue
            for q, diff in ((lit, "literal"), (ab, "abstract")):
                if q and len(q) > 10 and "?" in q:
                    fh.write(json.dumps({"q": q, "anchor": anc, "difficulty": diff,
                                         "source": c["source"], "target_tier": "P1"},
                                        ensure_ascii=False) + "\n")
                    n += 1
    print(f"{slug}: {n} пар ({k} чанков) → {out_path}")


if __name__ == "__main__":
    k = int(os.getenv("K", "20"))
    for slug in (sys.argv[1:] or list(AUTHORS)):
        run(slug, k, GOLDEN_MODEL)
