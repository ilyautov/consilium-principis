#!/usr/bin/env python3
"""Генератор синтетических eval-данных для Consilium-Principis.

1. gen_adversarial_ooc  — состязательные смежно-доменные OOC-вопросы (топиковый камуфляж)
2. gen_answerable       — обоснованные вопросы из P1-пассажей
3. gen_atomic_compounds — составные заявления со смешанной обоснованностью атомов

Все LLM-вызовы через llm_local.generate (мокируется в тестах — сеть не нужна).
CLI gated on llm_local.available() — если ollama недоступен, выходим с ошибкой, не генерируем мусор.
"""
import os
import sys
import json
import re
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_local
from corpusbuild.paths import corpus_path

# ── Тематические регистры по советнику (для prompt-инструкции) ────────────────
DOMAIN_THEMES = {
    "machiavelli": "power, statecraft, betrayal, military strategy, fortune, principalities",
    "marcus-aurelius": "Stoic virtue, mortality, self-discipline, duty, rational control",
}


# ── Корпусные helpers (мокируемый слой) ───────────────────────────────────────

def _load_chunks(advisor_dir):
    """Загружает чанки корпуса советника. Отдельная функция — легко монкипатчится в тестах."""
    path = corpus_path(advisor_dir)
    chunks = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def _stratified(chunks, k, min_len=350):
    """Равномерно по корпусу, пропуская служебные/короткие чанки."""
    good = [c for c in chunks if len(c.get("text", "")) > min_len
            and "# SOURCE:" not in c["text"][:40]]
    if len(good) <= k:
        return good
    step = len(good) / k
    return [good[int(i * step)] for i in range(k)]


def _anchor_of(text):
    """Самое длинное предложение (30..200 симв) — характерный якорь."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 30 <= len(s.strip()) <= 200]
    return max(sents, key=len) if sents else text[:100]


# ── Общий helper ───────────────────────────────────────────────────────────────

def write_jsonl(path, rows, advisor_dir=None):
    """Записать список dict-ов в JSONL-файл (UTF-8). Создаёт папки при необходимости.
    advisor_dir задан → первой строкой meta-запись с хэшем корпуса (§1.4: golden↔corpus
    версионирование; eval-лоадер громко предупредит при дрейфе корпуса)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if advisor_dir:
            from golden_meta import meta_record
            meta = meta_record(advisor_dir)
            if meta:
                fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── 1. Состязательные OOC ─────────────────────────────────────────────────────

def _parse_qwhy(text):
    """Парсит ответ LLM в список {"q","why"}.

    Формат одной строки: Q: <вопрос> | WHY: <причина>
    Любая строка, не соответствующая формату, молча отбрасывается (fail-closed).
    """
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"Q:\s*(.+?)\s*\|\s*WHY:\s*(.+)", line, re.I)
        if not m:
            continue
        q = m.group(1).strip()
        why = m.group(2).strip()
        if len(q) >= 15 and len(why) >= 10:
            results.append({"q": q, "why": why})
    return results


def gen_adversarial_ooc(advisor_dir, author, n, seed_failures=None, model=None):
    """Генерирует N состязательных OOC-вопросов с топиковым камуфляжем.

    Каждый вопрос ЗВУЧИТ как принадлежащий домену автора, но НЕ отвечается корпусом —
    потому что требует современной конкретики, внешних имён/событий, или затрагивает
    смежную под-тему, которую автор никогда не рассматривал.

    seed_failures: список {"q","why"} — предыдущие OOC, ошибочно засчитанные ретривом
    как «отвечаемые». Если передан, инжектируется в prompt как few-shot exemplары
    с инструкцией генерировать СЛОЖНЕЕ — это hook для рекурсивного ужесточения.
    """
    slug = os.path.basename(advisor_dir.rstrip("/"))
    themes = DOMAIN_THEMES.get(slug, "the author's thematic domain")

    seed_block = ""
    if seed_failures:
        examples = "\n".join(
            f'  - "{s["q"]}" ({s.get("why", "")})' for s in seed_failures[:5]
        )
        seed_block = (
            "\n\nPREVIOUS QUESTIONS THAT WERE TOO EASY (the retrieval system found plausible "
            "chunks for them anyway). Your new questions MUST be HARDER — more deceptively "
            "phrased, more narrowly modern, or requiring specific external referents the "
            "author never names:\n" + examples + "\n"
        )

    prompt = (
        f"You are generating adversarial evaluation questions for a retrieval-grounded AI advisor "
        f"whose corpus consists ONLY of {author}'s own writings "
        f"(thematic domain: {themes}).\n\n"
        f"Task: produce EXACTLY {n} questions that SOUND like they are in {author}'s domain "
        f"but CANNOT be answered from {author}'s corpus because they:\n"
        "  a) demand modern specifics (companies, tools, events, dates after the author's era), OR\n"
        "  b) reference named external people or places the author never discusses, OR\n"
        "  c) ask about an adjacent sub-topic the author never treats.\n\n"
        "CRITICAL — topical camouflage: every question must USE thematic vocabulary from the "
        "domain (power, virtue, strategy, fortune, duty…) so it FEELS like it belongs, "
        "yet be fundamentally unanswerable from the corpus.\n"
        + seed_block
        + "\nOutput format — EXACTLY one entry per line (nothing else, no numbering):\n"
        "Q: <question in Russian or English> | WHY: <one-line reason it is unanswerable>\n\n"
        f"Produce exactly {n} lines."
    )

    raw = llm_local.generate(prompt, model=model, temperature=0.7)
    results = _parse_qwhy(raw)
    return results[:n]


# ── 2. Обоснованные вопросы ────────────────────────────────────────────────────

def gen_answerable(advisor_dir, n, model=None):
    """Генерирует N обоснованных вопросов из P1-пассажей корпуса.

    Возвращает {"q","anchor","ref"}: вопрос, характерный якорь чанка, источник.
    Зеркалит стратегию gen_golden.py, но упрощённо (один вопрос на чанк).
    """
    chunks = _load_chunks(advisor_dir)
    samples = _stratified(chunks, n)
    results = []

    for c in samples:
        text = c["text"][:1200]
        source = c.get("source", "")
        anchor = _anchor_of(c["text"])

        prompt = (
            "Below is a passage from an author's own writing.\n"
            "Generate ONE question in Russian that THIS specific passage directly answers.\n"
            "The question must be specific to this passage's content, not generic.\n"
            "Do NOT quote the passage. Do NOT include an answer. Output only the question.\n\n"
            f"Passage:\n{text}\n"
        )
        raw = llm_local.generate(prompt, model=model, temperature=0.4)
        q = raw.strip().splitlines()[0].strip() if raw.strip() else ""
        if len(q) > 10:
            results.append({"q": q, "anchor": anchor[:150], "ref": source})

    return results


# ── 3. Атомарные компаунды ─────────────────────────────────────────────────────

def gen_atomic_compounds(advisor_dir, n, model=None):
    """Строит N составных заявлений с частичной обоснованностью.

    Каждый item: РЕАЛЬНАЯ P1-клауза (grounded=True) + ВЫДУМАННАЯ LLM клауза (grounded=False).
    Позволяет тестировать partial-grounding в атомарном eval (atomize / atomic_grounding).
    Детерминированно по seed=42, чтобы сэмпл был воспроизводим.
    """
    chunks = _load_chunks(advisor_dir)
    rng = random.Random(42)
    good = [c for c in chunks if len(c.get("text", "")) > 200]
    samples = rng.sample(good, min(n, len(good)))
    results = []

    for c in samples:
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", c["text"])
                 if len(s.strip()) >= 20]
        if not sents:
            continue
        real_clause = rng.choice(sents[:10])[:200]

        # LLM изобретает правдоподобную, но ОТСУТСТВУЮЩУЮ клаузу в стиле автора
        prompt = (
            "Given this real clause from a historical author's corpus:\n"
            f'"{real_clause}"\n\n'
            "Invent ONE plausible-sounding clause in the same style and thematic register "
            "that the author NEVER actually wrote — it should sound authentic but be fabricated. "
            "Output only the fabricated clause, no quotes, no preamble, one line."
        )
        raw = llm_local.generate(prompt, model=model, temperature=0.6)
        fake_clause = raw.strip().splitlines()[0].strip()[:200] if raw.strip() else "fabricated claim"

        compound_text = f"{real_clause}. {fake_clause}."
        results.append({
            "text": compound_text,
            "atoms": [
                {"text": real_clause, "grounded": True},
                {"text": fake_clause, "grounded": False},
            ],
        })

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    if not llm_local.available():
        print("ollama недоступен — генерацию синтетики прерываем (exit 1).", file=sys.stderr)
        sys.exit(1)

    cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "board_config.json",
    )
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(scripts_dir)
    golden_dir = os.path.join(scripts_dir, "golden")
    n = int(os.getenv("SYNTH_N", "15"))

    authors = {
        "machiavelli": "Niccolò Machiavelli",
        "marcus-aurelius": "Marcus Aurelius",
    }

    for slug, author in authors.items():
        adv_cfg = cfg.get("advisors", {}).get(slug, {})
        if adv_cfg.get("chunks", 0) == 0:
            print(f"[skip] {slug}: нет корпуса в board_config")
            continue

        advisor_dir = os.path.join(project_root, "advisors", slug)
        print(f"\n=== {slug} ({author}) ===")

        # 1. Adversarial OOC
        ooc = gen_adversarial_ooc(advisor_dir, author, n)
        path = os.path.join(golden_dir, f"{slug}.adversarial.jsonl")
        write_jsonl(path, ooc, advisor_dir=advisor_dir)
        print(f"  adversarial OOC : {len(ooc):3d} → {path}")
        for item in ooc[:3]:
            print(f"    • {item['q'][:80]}")
            print(f"      why: {item['why'][:70]}")

        # 2. Answerable
        ans = gen_answerable(advisor_dir, n)
        path = os.path.join(golden_dir, f"{slug}.synth_answerable.jsonl")
        write_jsonl(path, ans, advisor_dir=advisor_dir)
        print(f"  answerable      : {len(ans):3d} → {path}")

        # 3. Atomic compounds
        cmp = gen_atomic_compounds(advisor_dir, n)
        path = os.path.join(golden_dir, f"{slug}.synth_atomic.jsonl")
        write_jsonl(path, cmp, advisor_dir=advisor_dir)
        print(f"  atomic compounds: {len(cmp):3d} → {path}")


if __name__ == "__main__":
    main()
