"""Валидационный гейт корпуса: распределение тиров, флаг неразмеченного (A), инварианты рва."""
import json
from collections import Counter
from . import paths


def report(advisor_dir: str) -> dict:
    path = paths.corpus_path(advisor_dir)
    with open(path, encoding="utf-8") as f:
        chunks = [json.loads(l) for l in f if l.strip()]
    tiers = dict(Counter(c.get("tier", "A") for c in chunks))
    unlabeled = tiers.get("A", 0)
    ok = unlabeled == 0 and len(chunks) > 0
    print(f"[доктор] {advisor_dir}: чанков {len(chunks)}, тиры {tiers}")
    if unlabeled:
        print(f"  ⚠️  {unlabeled} чанков с тиром A (неразмечено/fail-closed) — разметь источник в манифесте")
    print(f"  {'✓ OK' if ok else '✗ ГЕЙТ НЕ ПРОЙДЕН'}")
    return {"ok": ok, "tiers": tiers, "chunks": len(chunks), "unlabeled": unlabeled}


def calibration(advisor_dir: str) -> dict:
    """Калибровочные инварианты графа (L2.3): нет безземельных кернелов; кросс-домен-enrichment
    обязан иметь traces_to_kernel. Возвращает {ok, groundless_kernels, untraced_cross_domain}."""
    import os
    from . import paths
    bd = paths.build_dir(advisor_dir)
    groundless = 0
    kp = os.path.join(bd, "kernels.json")
    if os.path.isfile(kp):
        groundless = sum(1 for k in json.load(open(kp, encoding="utf-8")) if not k.get("grounded_in"))
    untraced = 0
    ep = os.path.join(bd, "enrichment.jsonl")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    e = json.loads(line)
                    if e.get("kind") == "кросс-домен" and not e.get("traces_to_kernel"):
                        untraced += 1
    ok = groundless == 0 and untraced == 0
    print(f"[доктор-калибровка] {advisor_dir}: безземельных кернелов {groundless}, "
          f"кросс-домен без trace {untraced} → {'✓ OK' if ok else '✗ ГЕЙТ'}")
    return {"ok": ok, "groundless_kernels": groundless, "untraced_cross_domain": untraced}
