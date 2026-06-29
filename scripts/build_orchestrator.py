#!/usr/bin/env python3
"""Сборка советника в один шаг: манифест-гейт → corpus → kernels → отчёт готовности.

Чинит фрагментацию: pipeline.build доходит только до corpus.jsonl; kernels (gemma/ollama) и
эмбеддинги были отдельными ручными шагами. КЛЮЧЕВОЕ: манифест-гейт (validate_manifest) стоит
ПЕРЕД сборкой — сломанный манифест (region-маркер не в тексте → тиры съедут, 🔵 не на тех
словах) НЕ должен породить корпус. Kernels требуют ollama → graceful: нет сети → шаг помечается,
сборка не падает (corpus собран независимо).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manifest_builder import validate_manifest


def build_advisor_full(advisor_dir, author=None, run_kernels=True, run_index=True):
    """Манифест-гейт → corpus → (kernels) → (семантик-индекс) → отчёт. Возврат: {ok, steps, ...}."""
    steps = []
    sources_dir = os.path.join(advisor_dir, "sources")
    manifest_path = os.path.join(sources_dir, "manifest.json")

    # 1) МАНИФЕСТ-ГЕЙТ (ров): не строим корпус, если манифест ломает тиры
    if os.path.isfile(manifest_path):
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        val = validate_manifest(manifest, sources_dir)
        if not val["ok"]:
            return {"ok": False, "stopped_at": "manifest-validation",
                    "problems": val["problems"], "steps": steps}
        steps.append({"step": "manifest", "ok": True})
    else:
        steps.append({"step": "manifest", "ok": True, "note": "нет манифеста → всё P1 (бэк-компат)"})

    # 2) CORPUS (детерминированно, без модели)
    from corpusbuild import pipeline
    chunks = pipeline.build(advisor_dir)
    steps.append({"step": "corpus", "ok": True, "chunks": len(chunks)})

    # 3) KERNELS (gemma/ollama → graceful)
    if run_kernels:
        try:
            from corpusbuild import kernels
            ks = kernels.build_kernels(advisor_dir, author or os.path.basename(advisor_dir.rstrip("/")))
            steps.append({"step": "kernels", "ok": True, "count": len(ks)})
        except Exception as e:
            steps.append({"step": "kernels", "ok": False, "note": f"нужен ollama/gemma: {e}"})

    # 4) СЕМАНТИК-ИНДЕКС (ollama/bge-m3 → FULL-ретрив; без него остаёмся на полу, контур цел)
    if run_index:
        try:
            import tier_full
            if tier_full.available():
                tier_full.build_index(advisor_dir)
                steps.append({"step": "index", "ok": True})
            else:
                steps.append({"step": "index", "ok": False,
                              "note": "ollama/bge-m3 недоступен → SIMPLE (пол), контур цел"})
        except Exception as e:
            steps.append({"step": "index", "ok": False, "note": f"индекс не построен: {e}"})

    # 5) ОТЧЁТ готовности
    from preflight import _advisor_status
    return {"ok": True, "steps": steps, "status": _advisor_status(advisor_dir)}
