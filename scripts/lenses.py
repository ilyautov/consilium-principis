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

MARKER_CEILING = "🟡"


def _extract_kernels(sections):
    """Имена кернелов из секции `## Кернелы…` (строки `- **Имя:** …`)."""
    for title, body in sections.items():
        if title.startswith("Кернелы"):
            ks = []
            for line in body.splitlines():
                m = re.match(r"^-\s+\*\*(.+?)\*\*", line.strip())
                if m:
                    ks.append(m.group(1).rstrip(":").strip())
            return ks
    return []


def load_lens(path):
    """{name, grade, marker_ceiling, axis, kernels, fields, sections} или None если нет файла."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
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
        if fn.endswith(".md") and fn != "README.md":
            lens = load_lens(os.path.join(lenses_dir, fn))
            if lens:
                out.append(lens)
    return out


def is_frame_lens_honest(lens):
    """Инвариант: frame-lens НЕ может претендовать на 🔵 — её потолок обязан быть 🟡.
    Ловит нечестную конфигурацию (кто-то поставил marker_ceiling: 🔵 линзе без корпуса)."""
    return lens.get("grade") != "frame-lens" or lens.get("marker_ceiling") == "🟡"
