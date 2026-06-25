#!/usr/bin/env python3
"""Загрузчик модели Принцепса (`principis.md`) — кто ПЕРЕД советом (Consilium Principis).

Совет грузит это в начале заседания: память о юзере между сессиями, адаптация подачи
(interface_mode), журнал решений (семя петли исхода U1). Это приватные данные юзера
(gitignored): он владеет и правит, совет не меняет без его жеста (право-на-ревизию).

Формат: YAML-frontmatter (плоские key: value) + тело с секциями по `##`-заголовкам.
fail-safe: нет файла → ok=False, interface_mode='rigor' (дефолт в сторону строгости, не театра).
"""
import os
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from mdmeta import parse_frontmatter, parse_sections

DEFAULT_MODE = "rigor"      # fail-closed к строгому интерфейсу, а не к театру-поддержке
VALID_MODES = ("rigor", "support")


def load_principis(path):
    """{ok, interface_mode, owner, fields, sections}. Нет файла → ok=False, mode=rigor."""
    if not os.path.isfile(path):
        return {"ok": False, "interface_mode": DEFAULT_MODE, "owner": None,
                "fields": {}, "sections": {}}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fields, body = parse_frontmatter(text)
    mode = fields.get("interface_mode", DEFAULT_MODE)
    if mode not in VALID_MODES:
        mode = DEFAULT_MODE
    return {"ok": True, "interface_mode": mode, "owner": fields.get("owner"),
            "fields": fields, "sections": parse_sections(body)}
