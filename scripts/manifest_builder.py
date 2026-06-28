#!/usr/bin/env python3
"""Скаффолдер+валидатор тир-манифеста (sources/manifest.json) — спина доверяемой сборки.

Контур (🔵 = слова автора) держится на этом файле: каждый источник → тир (P1 слова автора /
S1 комментарий / B биография / A апокриф) + region-маркеры for/until. Писался руками.
Опасность: если region-маркер не встречается в источнике ДОСЛОВНО, тир молча съезжает и 🔵
даётся не на тех словах — реальная дыра рва. Поэтому:
  • scaffold_manifest(entries) — собрать JSON из структурных решений (тир определяет ризонинг);
  • validate_manifest(manifest, sources_dir) — ДЕТЕРМИНИРОВАННО проверить: файлы на месте, тиры
    валидны, region-маркеры реально есть в тексте. Без этого самосборка тихо ломает контур.
"""
import os

VALID_TIERS = ("P1", "P2", "S1", "S2", "B", "A")
_META_KEYS = ("attribution", "title", "translator", "lang", "license")


def scaffold_manifest(entries):
    """[{source, tier, [attribution/title/...], regions?}] → dict манифеста."""
    manifest = {}
    for e in entries:
        rec = {"tier": e["tier"]}
        for k in _META_KEYS:
            if e.get(k):
                rec[k] = e[k]
        if e.get("regions"):
            rec["regions"] = e["regions"]
        manifest[e["source"]] = rec
    return manifest


def validate_manifest(manifest, sources_dir):
    """Проверка целостности манифеста. {ok, problems:[{source, [marker], issue}]}.
    Главное — region-маркеры реально присутствуют в источнике (иначе тиры съедут молча)."""
    problems = []
    for src, rec in manifest.items():
        path = os.path.join(sources_dir, src)
        if not os.path.isfile(path):
            problems.append({"source": src, "issue": "file-missing"})
            continue
        if rec.get("tier") not in VALID_TIERS:
            problems.append({"source": src, "issue": f"bad-tier:{rec.get('tier')}"})
        text = open(path, encoding="utf-8", errors="ignore").read()
        for reg in rec.get("regions", []):
            if reg.get("tier") not in VALID_TIERS:
                problems.append({"source": src, "issue": f"bad-region-tier:{reg.get('tier')}"})
            for edge in ("from", "until"):
                marker = reg.get(edge)
                if marker and marker not in text:
                    problems.append({"source": src, "marker": marker,
                                     "issue": f"marker-not-in-source:{edge}"})
    return {"ok": not problems, "problems": problems}
