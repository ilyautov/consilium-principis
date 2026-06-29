#!/usr/bin/env python3
"""Стартовый совет в один шаг — курированный набор public-domain мудрецов для cold-start.

Чинит главную фрикцию «использования с нуля»: «пустая доска — норма» по философии, но новый
юзер упирается в холодный стол и собирает советников по одному. seed_council за один вызов:
для каждого PD-мудреца fetch (collect_pd, авто-strip Gutenberg) → запись ВЫВЕРЕННОГО манифеста
(тир + region-маркеры, выверенные под издание) → ВАЛИДАЦИЯ (манифест-гейт: маркер реально в
тексте) → build_advisor_full. Гейт встроен: сломанный маркер → советник не идёт в сборку.
Легальная граница соблюдена — только public-domain. fetch/build инъектируются (тест офлайн).

Реестр = выверенные манифесты: суждение о тирах сделано один раз за юзера. Расширяемый.
"""
import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manifest_builder import validate_manifest

# Курированные PD-мудрецы с выверенными под издание манифестами (region-маркеры проверены
# против конкретного gutenberg-издания; collect_pd срезает gutenberg-boilerplate до сохранения).
SEED_ADVISORS = [
    {
        "name": "marcus-aurelius", "display": "Марк Аврелий",
        "url": "https://www.gutenberg.org/cache/epub/2680/pg2680.txt",
        "source_file": "meditations-long-gutenberg.txt",
        "manifest_entry": {
            "tier": "P1", "attribution": "Marcus Aurelius", "title": "Meditations",
            "translator": "George Long", "lang": "en", "license": "public-domain",
            "regions": [
                {"tier": "B", "until": "THE FIRST BOOK"},
                {"tier": "P1", "from": "THE FIRST BOOK", "until": "APPENDIX"},
                {"tier": "S1", "from": "APPENDIX"},
            ],
        },
    },
    {
        "name": "epictetus", "display": "Эпиктет",
        "url": "https://www.gutenberg.org/cache/epub/45109/pg45109.txt",
        "source_file": "enchiridion-lla.txt",
        "manifest_entry": {
            "tier": "P1", "attribution": "Epictetus", "title": "The Enchiridion",
            "lang": "en", "license": "public-domain",
            "origin": "gutenberg.org/ebooks/45109 (Library of Liberal Arts ed.)",
            # секвенциальные from-маркеры: front matter → тело (с 'THE ENCHIRIDION') → каталог
            "regions": [
                {"tier": "B"},
                {"tier": "P1", "from": "THE ENCHIRIDION"},
                {"tier": "B", "from": "The Library of Liberal Arts"},
            ],
        },
    },
]


def seed_one(spec, root, fetch_fn, build_fn):
    """fetch → манифест → валидация-гейт → build. {name, ok, stage, ...}."""
    adv_dir = os.path.join(root, "advisors", spec["name"])
    sources = os.path.join(adv_dir, "sources")
    os.makedirs(sources, exist_ok=True)

    saved = fetch_fn(adv_dir, spec["url"], spec["source_file"])
    if not saved or not os.path.isfile(saved):
        return {"name": spec["name"], "ok": False, "stage": "fetch", "detail": "не скачалось"}

    fname = os.path.basename(saved)
    manifest = {fname: dict(spec["manifest_entry"])}
    json.dump(manifest, open(os.path.join(sources, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    val = validate_manifest(manifest, sources)
    if not val["ok"]:
        return {"name": spec["name"], "ok": False, "stage": "manifest", "problems": val["problems"]}

    res = build_fn(adv_dir)
    return {"name": spec["name"], "ok": bool(res.get("ok")), "stage": "build", "build": res}


def seed_council(specs, root, fetch_fn, build_fn):
    """Собрать набор; падение одного советника не валит остальных."""
    return [seed_one(s, root, fetch_fn, build_fn) for s in specs]


# ---------- реальные fetch/build для CLI ----------

def _real_fetch(adv_dir, url, source_file):
    name = source_file.rsplit(".", 1)[0]
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collect_pd.py")
    subprocess.run([sys.executable, script, adv_dir, "--url", url, "--name", name,
                    "--license", "public-domain"], check=True)
    sd = os.path.join(adv_dir, "sources")
    # collect_pd слугифицирует имя — находим .txt, соответствующий запросу
    cand = os.path.join(sd, source_file)
    if os.path.isfile(cand):
        return cand
    txts = [f for f in os.listdir(sd) if f.endswith(".txt")]
    return os.path.join(sd, txts[0]) if txts else None


def _real_build(adv_dir):
    from build_orchestrator import build_advisor_full
    return build_advisor_full(adv_dir, run_kernels=True)


def run_seed_council(root="."):
    return seed_council(SEED_ADVISORS, root, _real_fetch, _real_build)
