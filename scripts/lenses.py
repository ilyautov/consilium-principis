#!/usr/bin/env python3
"""Загрузчик функциональных линз (`lenses/`) — бизнес-функции как советники.

Линза = метод дисциплины (кернелы-фреймворки) БЕЗ авторского корпуса. Потолок маркера = 🟡:
🔵 невозможен by-design (нет corpus.jsonl → tier-aware гейт не найдёт P1/P2). Честность —
структурная, не на доверии. Отличие от persona-советников: те живут в advisors/ (приватно),
линзы — в lenses/ (генерик, часть скилла). См. lenses/README.md.
"""
import os
import re
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from mdmeta import parse_frontmatter, parse_sections
from corpusbuild.paths import corpus_path

MARKER_CEILING = "🟡"


def _extract_kernels(sections):
    """Имена кернелов из секции `## Кернелы…` (строки `- **Имя:** …`)."""
    for title, body in sections.items():
        if title.startswith("Кернелы"):
            ks = []
            for line in body.splitlines():
                # требуем двоеточие ВНУТРИ жирного: `- **Имя:** …` — иначе любой жирный буллет
                # (эмфаза/заметка) ложно попал бы в кернелы (ревью 2026-06-26).
                m = re.match(r"^-\s+\*\*(.+?):\*\*", line.strip())
                if m:
                    ks.append(m.group(1).strip())
            return ks
    return []


def _lens_md_path(path):
    """Путь к .md линзы. Flat frame-линза = сам файл `lenses/x.md`. Grounded-линза =
    каталог `lenses/x/` с `lens.md` внутри (рядом corpus.jsonl + sources/manifest.json)."""
    if os.path.isdir(path):
        return os.path.join(path, "lens.md")
    return path


def lens_has_corpus(path):
    """True ⟺ у линзы есть канон-корпус (grounded). Flat .md → нет. Каталог с корпусом → да.
    Путь корпуса резолвим через corpus_path (build/ → legacy lens-dir), не литералом."""
    if not os.path.isdir(path):
        return False
    return os.path.isfile(corpus_path(path))


def load_lens(path):
    """{name, grade, marker_ceiling, axis, kernels, fields, sections} или None если нет файла.
    path — flat-файл `x.md` ИЛИ каталог `x/` (grounded, с lens.md+corpus.jsonl)."""
    md = _lens_md_path(path)
    if not os.path.isfile(md):
        return None
    with open(md, encoding="utf-8") as f:
        text = f.read()
    fields, body = parse_frontmatter(text)
    sections = parse_sections(body)
    return {"name": fields.get("name"), "grade": fields.get("grade"),
            "marker_ceiling": fields.get("marker_ceiling", MARKER_CEILING),
            "axis": fields.get("axis"), "kernels": _extract_kernels(sections),
            "fields": fields, "sections": sections}


def list_lenses(lenses_dir):
    """Все линзы каталога (кроме README), отсортированы по имени файла."""
    out = []
    if not os.path.isdir(lenses_dir):
        return out
    for fn in sorted(os.listdir(lenses_dir)):
        full = os.path.join(lenses_dir, fn)
        if fn == "README.md":
            continue
        if fn.endswith(".md") or (os.path.isdir(full) and os.path.isfile(os.path.join(full, "lens.md"))):
            lens = load_lens(full)
            if lens:
                out.append(lens)
    return out


def is_lens_honest(lens, has_corpus):
    """Обобщённый инвариант честности маркер-потолка:
    🔵/🟢 (претензия на дословный/комментирующий авторитет) разрешён ⟺ есть канон-корпус.
    Нет корпуса, но потолок 🔵/🟢 → нечестно (авторитет без слов). Недо-претензия (есть
    корпус, потолок 🟡) — честна. Покрывает и frame-lens (нет корпуса → обязан 🟡), и
    grounded-lens (есть корпус → 🔵 законен)."""
    claims_authority = lens.get("marker_ceiling") in ("🔵", "🟢")
    if claims_authority and not has_corpus:
        return False
    return True


def is_frame_lens_honest(lens):
    """Back-compat: frame-lens (по определению без корпуса) не может претендовать на 🔵/🟢."""
    return is_lens_honest(lens, has_corpus=False) if lens.get("grade") == "frame-lens" else True
