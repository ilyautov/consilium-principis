"""Распознавание редакторского аппарата PD-изданий (вступление / инлайн-комментарий / приложения).
Чистый и ДЕТЕРМИНИРОВАННЫЙ: без ollama, без сети, без I/O. Контур: 🔵 только уверенно-авторскому
тексту вне [...]. Любая неопределённость → 🟢/drop, НИКОГДА 🔵."""
import re

# Лексикон классических толкователей (издания Giles/Legge Сунь-Цзы и пр.) + общие маркеры.
# frozenset → дедуп: любой случайный точный повтор схлопывается, чтобы count не двоился.
# Прямой И фигурный апострофы — РАЗНЫЕ строки (разные кодировки изданий), оба нужны.
_COMMENTATORS = frozenset((
    "Ts'ao Kung", "Ts’ao Kung", "Tu Mu", "Chang Yu", "Chang Yü", "Wang Hsi",
    "Li Ch'uan", "Li Ch’uan", "Mei Yao", "Chia Lin", "Tu Yu", "Ho Shih",
    "the commentator", "commentators", "scholiast"))
_FRONT_RE = re.compile(r"^\s*(CHAPTER\s+I\b|I\.\s|BOOK\s+I\b|PART\s+I\b)", re.I)
_BACK_RE = re.compile(r"^\s*(APPENDIX|BIBLIOGRAPHY|INDEX\b|FOOTNOTES|THE\s+END)\b", re.I)


def split_inline(text):
    """[(segment, role)], role ∈ {author, commentary}. author — вне [...]; всё в скобках (вкл.
    вложенные) — commentary; незакрытая скобка → остаток commentary (fail-closed вниз)."""
    out, buf, depth = [], [], 0

    def push(role):
        s = "".join(buf).strip()
        if s:
            out.append((s, role))
        buf.clear()

    for ch in text:
        if ch == "[":
            if depth == 0:
                push("author")
            depth += 1
            buf.append(ch)
        elif ch == "]":
            buf.append(ch)
            if depth > 0:
                depth -= 1
                if depth == 0:
                    push("commentary")
        else:
            buf.append(ch)
    if buf:
        push("commentary" if depth > 0 else "author")   # незакрытая скобка → вниз
    return out


_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")


def strip_sections(text, front_until=None, back_from=None):
    """Срез фронт/бэк-материи: всё ДО строки с front_until и ОТ строки с back_from. None → не резать.
    front_until ВКЛЮЧИТЕЛЬНО: строка с маркером остаётся первой строкой тела (start=i, не i+1).
    front_until берёт ПЕРВОЕ вхождение, back_from — ПОСЛЕДНЕЕ; при этом scan() сообщает ПЕРВОЕ
    вхождение back-маркера. Для источников с повторяющимся маркером передавай УНИКАЛЬНУЮ строку."""
    lines = text.splitlines()
    start, end = 0, len(lines)
    if front_until:
        for i, ln in enumerate(lines):
            if front_until in ln:
                start = i
                break
    if back_from:
        for i in range(len(lines) - 1, -1, -1):
            if back_from in lines[i]:
                end = i
                break
    return "\n".join(lines[start:end]).strip()


def clean(text, front_until=None, back_from=None):
    """Только слова автора: strip_sections + удалить инлайн [...]-спаны (повторно для вложенности)."""
    body = strip_sections(text, front_until, back_from)
    prev = None
    while prev != body:                       # вложенные [a [b] c] схлопываем итеративно
        prev = body
        body = _BRACKET_RE.sub("", body)
    return re.sub(r"[ \t]{2,}", " ", body).strip()


def _bracket_ratio(lines):
    nonblank = [l for l in lines if l.strip()]
    return (sum(1 for l in nonblank if "[" in l) / len(nonblank)) if nonblank else 0.0


def _first_line(lines, rx):
    for i, ln in enumerate(lines):
        if rx.match(ln):
            return i, ln.strip()
    return None, None


def scan(text):
    """Детерминированный отчёт об аппарате. Поле signals — СЛУЖЕБНОЕ (юзеру не показывать)."""
    lines = text.splitlines()
    bracket_ratio = _bracket_ratio(lines)
    commentator_hits = sum(text.count(c) for c in _COMMENTATORS)
    fi, front_marker = _first_line(lines, _FRONT_RE)
    bi, back_marker = _first_line(lines, _BACK_RE)
    front_ok = fi is not None and fi > 3              # есть что отрезать спереди
    back_ok = bi is not None
    bracket = bracket_ratio >= 0.25 or commentator_hits >= 5
    has_apparatus = bracket or front_ok or back_ok
    sample_app = next((l.strip() for l in lines if "[" in l and len(l.strip()) > 20), "")
    sample_auth = next((l.strip() for l in lines
                        if l.strip() and "[" not in l and len(l.strip()) > 20
                        and not any(c in l for c in _COMMENTATORS)), "")
    return {
        "has_apparatus": has_apparatus,
        "signals": {
            "bracket_ratio": round(bracket_ratio, 3),
            "commentator_hits": commentator_hits,
            "front_until": front_marker if front_ok else None,
            "back_from": back_marker if back_ok else None,
            "front_confident": front_ok,
            "back_confident": back_ok,
        },
        "needs_host_review": has_apparatus and not (front_ok and back_ok),
        "sample_author": sample_auth,
        "sample_apparatus": sample_app,
        "suggested_mode": "tier" if has_apparatus else "raw",
        "inline_commentary": "bracket" if bracket else None,
    }


def tier_records(recs, front_until=None, back_from=None,
                 front_confident=False, back_confident=False, inline="bracket"):
    """recs: [(loc, text)] → [{loc, text, tier}]. Секции-поля: drop если уверенно, иначе S1 (🟢,
    fail-closed). Тело: split_inline → author=P1 (🔵), commentary=S1 (🟢)."""
    texts = [t for _, t in recs]
    start, end = 0, len(recs)
    if front_until:
        for i, t in enumerate(texts):
            if front_until in t:
                start = i
                break
    if back_from:
        for i in range(len(texts) - 1, -1, -1):
            if back_from in texts[i]:
                end = i
                break
    out = []
    for i, (loc, text) in enumerate(recs):
        if i < start or i >= end:                     # поле (вступление/приложение)
            confident = front_confident if i < start else back_confident
            if confident:
                continue                              # уверенно аппарат → drop
            out.append({"loc": loc, "text": text, "tier": "S1"})   # неуверенно → 🟢
            continue
        if inline == "bracket":
            for seg, role in split_inline(text):
                out.append({"loc": loc, "text": seg, "tier": "P1" if role == "author" else "S1"})
        else:
            out.append({"loc": loc, "text": text, "tier": "P1"})
    return out
