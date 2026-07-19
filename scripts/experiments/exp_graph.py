#!/usr/bin/env python3
"""Граф-валидация (L2.3.3): рёбра 'заземляет' (кернел→P1) не выдуманы — заземляющие пассажи кернела
объясняют ОТЛОЖЕННЫЕ пассажи лучше случайных рёбер. Перестановочный тест.

ВНИМАНИЕ — ТЕСТ СМЕЩЁН И ИЛЛ-ПОСТАВЛЕН (прогон 2026-06-26 дал 35.7%, own<null):
  (1) Геометрия: own = max-cos к ТЕСНОМУ кластеру (5 ближайших к кернелу), null = к 5 СЛУЧАЙНЫМ
      (разброс по корпусу). Для случайного held-out max к разбросу почти всегда выше → own<null
      по построению, независимо от качества рёбер.
  (2) Не та цель: заземление = детерминированный nearest-neighbor, его НЕЛЬЗЯ нагаллюцинировать.
      Галлюцинирует LLM-ЭНРИЧМЕНТ (enrichment.derived_from / кросс-домен traces) — вот что надо
      валидировать. Кернелы как таковые уже провалидированы дискриминативно (exp_kernels, 64-91%).
TODO: переписать на валидацию ЭНРИЧМЕНТ-рёбер (held-out предсказание), а не детерминир. заземления.
"""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # experiments/ → scripts/
from corpusbuild import embed, ids, paths

ADV = sys.argv[1] if len(sys.argv) > 1 else "advisors/machiavelli"
SEED = int(os.getenv("EXP_SEED", "7"))


def main():
    random.seed(SEED)
    corpus = ids.load_corpus(ADV)
    p1 = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c["text"]) > 250]
    kp = os.path.join(paths.build_dir(ADV), "kernels.json")
    with open(kp, encoding="utf-8") as f:
        kernels = json.load(f)
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
    # вердикт проверяет НАПРАВЛЕНИЕ: успех = own>null ЗНАЧИМО ВЫШЕ 50% (z>1.96), а не просто |z|>1.96
    if z > 1.96:
        sig = "✓ заземление держится (own>null значимо)"
    elif z < -1.96:
        sig = "✗ own<null значимо — НО см. оговорку в docstring: тест смещён (кластер vs разброс), не вывод о галлюцинации"
    else:
        sig = "✗ не значимо"
    print(f"=== граф-валидация {ADV}: own>null {wins}/{total} = {p:.1%}  z={z:+.2f}  {sig} ===")
    print("ВЫВОД: рёбра заземления не галлюцинированы, если own>null значимо ВЫШЕ 50%. "
          "Текущий тест смещён (см. docstring) — нужна валидация энричмент-рёбер.")


if __name__ == "__main__":
    main()
