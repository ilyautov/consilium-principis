"""Провенанс: тир происхождения по источнику (+ региону внутри файла) из sources/manifest.json.
FAIL-CLOSED: нет манифеста ИЛИ источник вне манифеста → A (🟡). 🔵 требует ЯВНОГО объявления
провенанса (P1/P2 в манифесте) — некурированный/вставленный текст синим не становится."""
import os, json

_CACHE = {}


def load_manifest(advisor_dir: str) -> dict:
    path = os.path.join(advisor_dir, "sources", "manifest.json")
    key = (path, os.path.getmtime(path)) if os.path.isfile(path) else (path, 0)
    if key not in _CACHE:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                _CACHE[key] = json.load(f)
        else:
            _CACHE[key] = None
    return _CACHE[key]


def tier_for(source: str, line_no: int, advisor_dir: str) -> str:
    """Тир без знания текста (плоский). Для пер-регионного — tier_for_line."""
    man = load_manifest(advisor_dir)
    if man is None:
        return "A"
    entry = man.get(source)
    if entry is None:
        return "A"
    return entry.get("tier", "A")


def tier_for_line(source: str, line_no: int, lines, advisor_dir: str) -> str:
    """Пер-регионный тир. СЕКВЕНЦИАЛЬНО: продвигаемся к региону k+1 только встретив его
    'from'-маркер ПО ПОРЯДКУ (находясь в регионе k). Так форвард-ссылка в оглавлении
    (напр. 'APPENDIX' в TOC ДО тела) не переключает регион преждевременно.
    Если ОДНА строка несёт маркеры нескольких регионов — строка относится к САМОМУ
    ДАЛЬНЕМУ (промежуточные регионы пусты); поэтому маркеры в манифесте должны быть
    различимыми строками на разных строках источника."""
    man = load_manifest(advisor_dir)
    if man is None:
        return "A"
    entry = man.get(source)
    if entry is None:
        return "A"
    regions = entry.get("regions")
    if not regions:
        return entry.get("tier", "A")
    ridx = 0
    for i in range(line_no + 1):
        ln = lines[i]
        while ridx + 1 < len(regions):
            mk = regions[ridx + 1].get("from")
            if mk and mk in ln:
                ridx += 1
            else:
                break
    return regions[ridx]["tier"]
