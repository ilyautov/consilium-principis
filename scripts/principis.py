#!/usr/bin/env python3
"""Загрузчик модели Принцепса (`principis.md`) — кто ПЕРЕД советом (Consilium Principis).

Совет грузит это в начале заседания: память о юзере между сессиями, адаптация подачи
(interface_mode), журнал решений (семя петли исхода U1). Это приватные данные юзера
(gitignored): он владеет и правит, совет не меняет без его жеста (право-на-ревизию).

Формат: YAML-frontmatter (плоские key: value) + тело с секциями по `##`-заголовкам.
fail-safe: нет файла → ok=False, interface_mode='rigor' (дефолт в сторону строгости, не театра).
"""
import os
import re

DEFAULT_MODE = "rigor"      # fail-closed к строгому интерфейсу, а не к театру-поддержке
VALID_MODES = ("rigor", "support")


def _parse_frontmatter(text):
    """Возвращает (fields: dict, body: str). Inline-комментарии после '#' срезаются."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    fields = {}
    for line in fm_raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.split("#", 1)[0].strip()       # срезать inline-комментарий
        fields[key.strip()] = val
    return fields, body


def _parse_sections(body):
    """Тело по `##`-заголовкам → {заголовок: текст}."""
    sections, cur, buf = {}, None, []
    for line in body.splitlines():
        h = re.match(r"^##\s+(.*)$", line)
        if h:
            if cur is not None:
                sections[cur] = "\n".join(buf).strip()
            cur, buf = h.group(1).strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        sections[cur] = "\n".join(buf).strip()
    return sections


def load_principis(path):
    """{ok, interface_mode, owner, fields, sections}. Нет файла → ok=False, mode=rigor."""
    if not os.path.isfile(path):
        return {"ok": False, "interface_mode": DEFAULT_MODE, "owner": None,
                "fields": {}, "sections": {}}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fields, body = _parse_frontmatter(text)
    mode = fields.get("interface_mode", DEFAULT_MODE)
    if mode not in VALID_MODES:
        mode = DEFAULT_MODE
    return {"ok": True, "interface_mode": mode, "owner": fields.get("owner"),
            "fields": fields, "sections": _parse_sections(body)}
