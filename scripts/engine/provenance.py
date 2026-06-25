"""Провенанс: тир происхождения по источнику (+ региону внутри файла) из sources/manifest.json.
Нет манифеста → всё P1 (бэк-компат). Источник вне манифеста → A (fail-closed, см. спеку §1)."""
import os, json

_CACHE = {}


def load_manifest(advisor_dir: str) -> dict:
    path = os.path.join(advisor_dir, "sources", "manifest.json")
    key = (path, os.path.getmtime(path)) if os.path.isfile(path) else (path, 0)
    if key not in _CACHE:
        _CACHE[key] = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else None
    return _CACHE[key]


def tier_for(source: str, line_no: int, advisor_dir: str) -> str:
    """Тир без знания текста (плоский). Для пер-регионного — tier_for_line."""
    man = load_manifest(advisor_dir)
    if man is None:
        return "P1"
    entry = man.get(source)
    if entry is None:
        return "A"
    return entry.get("tier", "A")


def tier_for_line(source: str, line_no: int, lines, advisor_dir: str) -> str:
    """Пер-регионный тир: идёт по lines[0..line_no], переключая регион на маркерах from/until."""
    man = load_manifest(advisor_dir)
    if man is None:
        return "P1"
    entry = man.get(source)
    if entry is None:
        return "A"
    regions = entry.get("regions")
    if not regions:
        return entry.get("tier", "A")
    cur = entry.get("tier", "A")
    seen = regions[0]["tier"] if "from" not in regions[0] else cur
    for i in range(line_no + 1):
        ln = lines[i]
        for r in regions:
            mk = r.get("from") or r.get("until")
            if mk and mk in ln:
                seen = r["tier"]
    return seen
