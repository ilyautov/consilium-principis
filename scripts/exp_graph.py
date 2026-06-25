#!/usr/bin/env python3
"""Граф-валидация (L2.3.3): рёбра 'заземляет' (кернел→P1) не выдуманы — заземляющие пассажи кернела
объясняют ОТЛОЖЕННЫЕ пассажи лучше случайных рёбер. Перестановочный тест.

Метод: для каждого кернела взять его grounded_in (заземление) как «якоря»; held-out = прочие P1.
own = средний max-cos held-out к якорям своего кернела; null = к случайным якорям той же мощности.
Доля own>null vs 50% — биномиальный/перестановочный.
"""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild import embed, ids, paths

ADV = sys.argv[1] if len(sys.argv) > 1 else "advisors/machiavelli"
SEED = int(os.getenv("EXP_SEED", "7"))


def main():
    random.seed(SEED)
    corpus = ids.load_corpus(ADV)
    p1 = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c["text"]) > 250]
    byid = {c["id"]: c for c in p1}
    kp = os.path.join(paths.build_dir(ADV), "kernels.json")
    kernels = json.load(open(kp, encoding="utf-8"))
    vecs = {c["id"]: v for c, v in zip(p1, embed.embed_texts([c["text"] for c in p1]))}
    allids = list(vecs)
    wins = total = 0
    for k in kernels:
        anchors = [a for a in k.get("grounded_in", []) if a in vecs]
        if len(anchors) < 2:
            continue
        held = [i for i in allids if i not in set(anchors)]
        rnd = random.sample(held, len(anchors))
        for hid in held:
            hv = vecs[hid]
            own = max(embed.cosine(hv, vecs[a]) for a in anchors)
            null = max(embed.cosine(hv, vecs[a]) for a in rnd)
            wins += own > null; total += 1
    p = wins / total if total else 0.0
    import math
    z = (p - 0.5) / math.sqrt(0.25 / total) if total else 0.0
    sig = "✓ значимо" if abs(z) > 1.96 else "✗ не значимо"
    print(f"=== граф-валидация {ADV}: own>null {wins}/{total} = {p:.1%}  z={z:+.2f}  {sig} ===")
    print("ВЫВОД: рёбра заземления не галлюцинированы, если own>null значимо выше 50%.")


if __name__ == "__main__":
    main()
