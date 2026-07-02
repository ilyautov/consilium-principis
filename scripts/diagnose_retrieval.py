#!/usr/bin/env python3
"""Диагностика ретрива: РАНГ anchor'а в выдаче (не только top-1).

Колонки:
  sem   — чистая семантика на исходном (RU) запросе = текущий прод.
  hyb   — Левер 1: HybridEngine (semantic ∪ lexical через RRF), семантика на RU-вопросе +
          лексика на EN-переводе (query_lex) = реальный прод-режим (LLM-слой переводит для лексики).

Разводит/меряет: H1 (кросс-язык) — отдельным RU↔EN прогоном (см. git-историю), здесь — лифт гибрида.
Зовёт движок напрямую (resolve_engine prefer=...), top_k=20.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval as E
import engine as ENG

TOP_K = 20

def _text(h):
    return h.get("text", "") if isinstance(h, dict) else getattr(h, "text", "")

def rank_in(hits, anchor):
    na = E.norm(anchor)
    for i, h in enumerate(hits, 1):
        if na in E.norm(_text(h)):
            return i
    return None

def load(path):
    from golden_meta import split_meta                # §1.4: _meta-строка ≠ golden-запись
    return split_meta([json.loads(l) for l in open(path, encoding="utf-8") if l.strip()])[1]

def recall(ranks, k):
    return sum(1 for r in ranks if r is not None and r <= k)

def run(slug):
    adv = f"advisors/{slug}"
    ru = load(f"scripts/golden/{slug}.retrieval.jsonl")
    en = load(f"scripts/golden/{slug}.retrieval.en.jsonl")
    sem_eng = ENG.resolve_engine(adv, prefer="semantic")
    hyb_eng = ENG.resolve_engine(adv, prefer="hybrid")
    print(f"\n{'='*72}\n{slug}\n{'='*72}\n{'anchor':40} {'sem':>4} {'hyb':>4}")
    rs, rh = [], []
    for a, b in zip(ru, en):
        s = rank_in(sem_eng.retrieve(a["q"], adv, top_k=TOP_K), a["anchor"])
        h = rank_in(hyb_eng.retrieve(a["q"], adv, top_k=TOP_K, query_lex=b["q"]), a["anchor"])
        rs.append(s); rh.append(h)
        f = lambda x: "—" if x is None else str(x)
        print(f"{a['anchor'][:38]:40} {f(s):>4} {f(h):>4}")
    n = len(rs)
    print("-"*72)
    for name, ranks in (("sem", rs), ("hyb", rh)):
        print(f"  {name}: top1={recall(ranks,1)}/{n}  @3={recall(ranks,3)}/{n}  "
              f"@5={recall(ranks,5)}/{n}  @10={recall(ranks,10)}/{n}  "
              f"miss(>{TOP_K})={sum(1 for r in ranks if r is None)}/{n}")

if __name__ == "__main__":
    for slug in (sys.argv[1:] or ["machiavelli", "marcus-aurelius"]):
        run(slug)
