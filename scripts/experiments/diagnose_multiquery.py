#!/usr/bin/env python3
"""Левер 2 замер: single hybrid (Левер 1) vs multi-query@N (сетка из линз → RRF).

Меряет РАНГ anchor'а: один запрос против N перефразировок-через-линзы. Ищем «колено» (3 vs 5)
и — главное — трещит ли МЕТАФОРНЫЙ барьер (промахи, что мажут оба бэкенда одним запросом).
Генератор вариантов вслепую к anchor (только вопрос + линзы из persona.md). Печатает варианты.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # experiments/ → scripts/
import eval as E
import engine as ENG
from engine.multi_query import generate_variants, multiquery_retrieve

TOP_K = 20

def _text(h): return h.get("text", "") if isinstance(h, dict) else getattr(h, "text", "")

def rank_in(hits, anchor):
    na = E.norm(anchor)
    for i, h in enumerate(hits, 1):
        if na in E.norm(_text(h)):
            return i
    return None

def lenses_of(adv):
    try:
        m = re.search(r"^lenses:\s*\[(.*?)\]", open(f"{adv}/persona.md", encoding="utf-8").read(), re.M)
        return [x.strip() for x in m.group(1).split(",")] if m else []
    except Exception:
        return []

def run(slug, n_variants=6):
    adv = f"advisors/{slug}"
    from golden_meta import split_meta                # §1.4: _meta-строка ≠ golden-запись
    ru = split_meta([json.loads(l) for l in open(f"scripts/golden/{slug}.retrieval.jsonl") if l.strip()])[1]
    en = split_meta([json.loads(l) for l in open(f"scripts/golden/{slug}.retrieval.en.jsonl") if l.strip()])[1]
    lenses = lenses_of(adv)
    hyb = ENG.resolve_engine(adv, prefer="hybrid")
    print(f"\n{'='*74}\n{slug}   линзы: {lenses}\n{'='*74}")
    print(f"{'anchor':40} {'1-hyb':>6} {'mq@3':>5} {'mq@5':>5}")
    r1, r3, r5 = [], [], []
    for a, b in zip(ru, en):
        single = rank_in(hyb.retrieve(a["q"], adv, top_k=TOP_K, query_lex=b["q"]), a["anchor"])
        variants = generate_variants(a["q"], lenses, n=n_variants)  # вслепую к anchor
        # фикс A: оригинал (EN) всегда в слиянии → пол не ниже single-hybrid
        m3 = rank_in(multiquery_retrieve(hyb, adv, [b["q"]] + variants[:3], top_k=TOP_K), a["anchor"])
        m5 = rank_in(multiquery_retrieve(hyb, adv, [b["q"]] + variants[:5], top_k=TOP_K), a["anchor"])
        r1.append(single); r3.append(m3); r5.append(m5)
        f = lambda x: "—" if x is None else str(x)
        print(f"{a['anchor'][:38]:40} {f(single):>6} {f(m3):>5} {f(m5):>5}")
        print(f"    variants: {variants[:5]}")
    n = len(r1)
    rec = lambda rs, k: sum(1 for r in rs if r is not None and r <= k)
    print("-"*74)
    for name, rs in (("1-hyb", r1), ("mq@3", r3), ("mq@5", r5)):
        print(f"  {name}: top1={rec(rs,1)}/{n}  @3={rec(rs,3)}/{n}  @5={rec(rs,5)}/{n}  "
              f"@10={rec(rs,10)}/{n}  miss={sum(1 for r in rs if r is None)}/{n}")

if __name__ == "__main__":
    for slug in (sys.argv[1:] or ["machiavelli", "marcus-aurelius"]):
        run(slug)
