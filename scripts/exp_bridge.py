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
    # СТРАТИФИЦИРОВАННЫЙ gold: links Тарасова покрывают только Prince → берём ~поровну Prince/Discourses,
    # чтобы на Prince-подвыборке (домен моста) была статистическая мощность.
    prince = [c for c in p1 if "prince" in c["source"]]
    disc = [c for c in p1 if "discourses" in c["source"]]
    n_pr = min(N // 2, len(prince))
    n_di = min(N - n_pr, len(disc))
    gold = random.sample(prince, n_pr) + random.sample(disc, n_di)
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
    covered = {dst for dsts in links.values() for dst in dsts}   # потолок моста: достижимые P1-чанки

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

    def rrf(rankings, c0=60):
        """Reciprocal Rank Fusion — честное слияние: ни один список не «хоронит» другой.
        score(d) = Σ 1/(c0 + rank_d). Стандартное score-agnostic слияние ранжирований."""
        score = {}
        for r in rankings:
            for rank, pid in enumerate(r):
                score[pid] = score.get(pid, 0.0) + 1.0 / (c0 + rank)
        return [pid for pid, _ in sorted(score.items(), key=lambda t: -t[1])]

    def dom(g):
        return "prince" if "prince" in g["source"] else "disc"

    conds = ("B0", "B1", "T", "T+B1")
    scopes = ("all", "prince", "disc")
    agg = {sc: {c: {1: 0, 5: 0, 10: 0} for c in conds} for sc in scopes}
    cnt = {sc: 0 for sc in scopes}
    paired = {sc: [] for sc in scopes}   # (B1@5 hit, T+B1@5 hit) — для McNemar
    for g in gold:
        q_ru = make_query_ru(g["text"])
        q_en = translate_to_en(q_ru)
        v_ru = embed.embed_texts([q_ru])[0]
        v_en = embed.embed_texts([q_en])[0]
        ranks = {"B0": rank_p1(v_ru), "B1": rank_p1(v_en), "T": rank_via_bridge(v_ru)}
        ranks["T+B1"] = rrf([ranks["T"], ranks["B1"]])   # честное слияние (RRF, не concat)
        for sc in ("all", dom(g)):
            cnt[sc] += 1
            for cond in conds:
                for k, hit in recall_at(ranks[cond], g["id"]).items():
                    agg[sc][cond][k] += hit
            paired[sc].append((int(g["id"] in ranks["B1"][:5]), int(g["id"] in ranks["T+B1"][:5])))

    def mcnemar(pairs):
        b = sum(1 for hb1, htb1 in pairs if hb1 and not htb1)
        c = sum(1 for hb1, htb1 in pairs if htb1 and not hb1)
        chi = ((abs(b - c) - 1) ** 2) / (b + c) if (b + c) else 0.0
        return b, c, chi, ("✓ значимо (p<0.05)" if chi > 3.84 else "✗ не значимо")

    n_pr_cov = sum(1 for g in gold if dom(g) == "prince" and g["id"] in covered)
    n_pr_tot = sum(1 for g in gold if dom(g) == "prince")
    print(f"\n=== Exp A: {ADV}, сид={SEED} (links Тарасова покрывают только Prince) ===")
    print(f"потолок моста: {len(covered)} уникальных P1-чанков достижимо через links "
          f"({len(covered)}/{len(prince)} Prince-чанков); из Prince-gold покрыто {n_pr_cov}/{n_pr_tot}")
    for sc in scopes:
        ns = cnt[sc]
        if not ns:
            continue
        print(f"\n— {sc} (N={ns}) —")
        for cond in conds:
            print(f"  {cond:5} r@1={agg[sc][cond][1]/ns:.0%}  r@5={agg[sc][cond][5]/ns:.0%}  r@10={agg[sc][cond][10]/ns:.0%}")
        b, c, chi, sig = mcnemar(paired[sc])
        print(f"  McNemar T+B1 vs B1 @5: b={b} c={c} χ²={chi:.2f} {sig}")
    print("\nHEADLINE = строка 'prince' (домен покрытия моста): мост реален, если там T+B1>B1 значимо. "
          "На 'all' эффект разбавлен Discourses, где у моста нет покрытия.")


if __name__ == "__main__":
    main()
