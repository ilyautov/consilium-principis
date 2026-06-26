#!/usr/bin/env python3
"""Преднастройка заседания — что готово к созыву совета (зовётся в начале сессии).

Собирает в одну картину три слоя: Принцепс (кто ПЕРЕД советом + interface_mode),
persona-советники (грунт корпуса/тиры/кернелы → могут ли давать 🔵), функциональные линзы
(деловые углы, потолок 🟡). Совет видит, кого может посадить и кого знает за столом.
"""
import os
import json
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from principis import load_principis
from lenses import list_lenses
from corpusbuild.paths import corpus_path, build_dir


def _advisor_status(adv_dir):
    cp = corpus_path(adv_dir)
    tiers, chunks = {}, 0
    if os.path.isfile(cp):
        with open(cp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line).get("tier", "?")
                except Exception:
                    continue
                tiers[t] = tiers.get(t, 0) + 1
                chunks += 1
    # кернелы всегда в build/ (не рядом с легаси-корпусом в корне) — ревью 2026-06-26
    has_kernels = os.path.isfile(os.path.join(build_dir(adv_dir), "kernels.json"))
    blue = tiers.get("P1", 0) + tiers.get("P2", 0) > 0
    return {"name": os.path.basename(adv_dir.rstrip("/")), "chunks": chunks, "tiers": tiers,
            "has_corpus": chunks > 0, "blue_eligible": blue, "has_kernels": has_kernels}


def preflight(root="."):
    """{principis, advisors[], lenses[], ready}. ready = есть ≥1 грунтованный советник И ≥1 линза."""
    principis = load_principis(os.path.join(root, "principis.md"))
    advisors = []
    adv_root = os.path.join(root, "advisors")
    if os.path.isdir(adv_root):
        for d in sorted(os.listdir(adv_root)):
            p = os.path.join(adv_root, d)
            if os.path.isdir(p):
                advisors.append(_advisor_status(p))
    lenses = [{"name": l["name"], "axis": l["axis"]} for l in list_lenses(os.path.join(root, "lenses"))]
    ready = any(a["has_corpus"] for a in advisors) and len(lenses) >= 1
    return {"principis": {"ok": principis["ok"], "interface_mode": principis["interface_mode"]},
            "advisors": advisors, "lenses": lenses, "ready": ready}


def _report(pf):
    lines = ["=== Преднастройка заседания ==="]
    pr = pf["principis"]
    lines.append(f"Принцепс: {'загружен' if pr['ok'] else 'нет профиля (дефолт)'} · подача={pr['interface_mode']}")
    lines.append("Советники (persona):")
    for a in pf["advisors"]:
        mark = "🔵-готов" if a["blue_eligible"] else ("грунт-есть" if a["has_corpus"] else "ПУСТО")
        k = "+кернелы" if a["has_kernels"] else "без кернелов"
        lines.append(f"  • {a['name']:<18} {a['chunks']:>5} чанков {dict(a['tiers'])}  {mark} {k}")
    lines.append("Функциональные линзы (потолок 🟡):")
    for l in pf["lenses"]:
        lines.append(f"  • {l['name']} — ось: {l['axis']}")
    lines.append(f"Готовность к созыву: {'✓ ДА' if pf['ready'] else '✗ нет (нужен грунтованный советник + линза)'}")
    return "\n".join(lines)


if __name__ == "__main__":
    root = _sys.argv[1] if len(_sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(_report(preflight(root)))
