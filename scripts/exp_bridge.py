#!/usr/bin/env python3
"""Эксперимент A: добавляет ли русский Тарасов-мост recall P1-якорей над translate-query?

Powered-набор (back-translation, не круговой): held-out P1-пассаж → LLM пишет русский ситуац-вопрос,
ответ=пассаж → gold=пассаж. Условия: B0 (наивный RU→P1), B1 (translate-query RU→EN→P1),
T (RU→Тарасов→links→P1), T+B1. Метрика recall@k, значимость McNemar (T+B1 vs B1).
"""
import os, sys, json, urllib.request, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild import embed, ids, paths

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GEN_MODEL = os.getenv("KERNEL_MODEL", "gemma3:27b")
ADV = sys.argv[1] if len(sys.argv) > 1 else "advisors/machiavelli"
N = int(os.getenv("EXP_N", "100"))
SEED = int(os.getenv("EXP_SEED", "7"))


def _gen(prompt, temp=0.4):
    body = json.dumps({"model": GEN_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": temp}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("response", "").strip()


def make_query_ru(passage):
    return _gen(f"Английский пассаж Макиавелли:\n{passage[:700]}\n\nСформулируй ОДИН короткий вопрос "
                f"ПО-РУССКИ о реальной ситуации, ответ на который даёт именно этот пассаж. Только вопрос.")


def translate_to_en(q_ru):
    return _gen(f"Translate to English, output only the translation:\n{q_ru}", temp=0.0)


def recall_at(ranked_ids, gold_id, ks=(1, 5, 10)):
    return {k: int(gold_id in ranked_ids[:k]) for k in ks}


def main():
    random.seed(SEED)
    corpus = ids.load_corpus(ADV)
    p1 = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c["text"]) > 300]
    s1 = [c for c in corpus if c["tier"] in ("S1", "S2")]
    gold = random.sample(p1, min(N, len(p1)))
    train_p1 = [c for c in p1]
    p1vec = embed.embed_texts([c["text"] for c in train_p1])
    p1ids = [c["id"] for c in train_p1]
    s1vec = embed.embed_texts([c["text"] for c in s1])
    links = {}
    lp = os.path.join(paths.build_dir(ADV), "links.jsonl")
    with open(lp, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                l = json.loads(line); links.setdefault(l["src"], []).append(l["dst"])

    def rank_p1(qvec):
        scored = sorted(zip(p1ids, (embed.cosine(qvec, v) for v in p1vec)), key=lambda t: -t[1])
        return [pid for pid, _ in scored]

    def rank_via_bridge(qvec):
        s1ranked = sorted(zip([c["id"] for c in s1], (embed.cosine(qvec, v) for v in s1vec)),
                          key=lambda t: -t[1])
        out = []
        for sid, _ in s1ranked:
            for pid in links.get(sid, []):
                if pid not in out:
                    out.append(pid)
        return out

    agg = {c: {1: 0, 5: 0, 10: 0} for c in ("B0", "B1", "T", "T+B1")}
    paired = {1: [], 5: [], 10: []}
    for g in gold:
        q_ru = make_query_ru(g["text"])
        q_en = translate_to_en(q_ru)
        v_ru = embed.embed_texts([q_ru])[0]
        v_en = embed.embed_texts([q_en])[0]
        r_b0 = rank_p1(v_ru)
        r_b1 = rank_p1(v_en)
        r_t = rank_via_bridge(v_ru)
        r_tb1 = r_t + [pid for pid in r_b1 if pid not in r_t]
        for cond, r in (("B0", r_b0), ("B1", r_b1), ("T", r_t), ("T+B1", r_tb1)):
            for k, hit in recall_at(r, g["id"]).items():
                agg[cond][k] += hit
        for k in (1, 5, 10):
            paired[k].append((int(g["id"] in r_b1[:k]), int(g["id"] in r_tb1[:k])))

    n = len(gold)
    print(f"\n=== Exp A: {ADV}, N={n}, сид={SEED} ===")
    for cond in ("B0", "B1", "T", "T+B1"):
        print(f"{cond:5} recall@1={agg[cond][1]/n:.2%}  @5={agg[cond][5]/n:.2%}  @10={agg[cond][10]/n:.2%}")
    b, c = 0, 0
    for hb1, htb1 in paired[5]:
        b += (hb1 and not htb1); c += (htb1 and not hb1)
    import math
    chi = ((abs(b - c) - 1) ** 2) / (b + c) if (b + c) else 0.0
    sig = "✓ значимо (p<0.05)" if chi > 3.84 else "✗ не значимо"
    print(f"\nMcNemar T+B1 vs B1 @5: discordant b={b} c={c}  χ²={chi:.2f}  {sig}")
    print("ВЫВОД: мост полезен, если T+B1 > B1 и McNemar значим; иначе — театр, энричмент не оправдан.")


if __name__ == "__main__":
    main()
