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
