"""Общий разбор markdown с YAML-frontmatter: используется principis.py и lenses.py.
Плоский key: value во frontmatter (без вложенности), тело по `##`-секциям. Без зависимостей."""
import re


def parse_frontmatter(text):
    """(fields: dict, body: str). Inline-комментарии после '#' в значении срезаются."""
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
        val = val.split("#", 1)[0].strip()
        fields[key.strip()] = val
    return fields, body


def parse_sections(body):
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
