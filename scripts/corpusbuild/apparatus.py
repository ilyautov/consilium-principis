"""Распознавание редакторского аппарата PD-изданий (вступление / инлайн-комментарий / приложения).
Чистый и ДЕТЕРМИНИРОВАННЫЙ: без ollama, без сети, без I/O.

ИНЛАЙН-гейт (внутри тела): 🔵 только уверенно-авторскому тексту вне [...]; любая неопределённость
в скобках (вложенность/незакрытая/сноска-определение) → 🟢/commentary, НИКОГДА 🔵 — абсолютно.

ГРАНИЦЫ секций (где кончается вступление, где начинаются приложения) в tier-режиме безопасны
ЧЕРЕЗ needs_host_review: если фронт/бэк не разрешились уверенно (start=0 / нет валидного хвоста),
scan поднимает needs_host_review=True для хоста (rule 10) — это НЕ абсолютный drop, а host-gate.

#55: back-срез засчитывается уверенным, только если кандидат лежит в хвостовых ~30% файла
(_is_trailing) — иначе это, вероятно, ВНУТРЕННЯЯ секция (напр. библиография научного PD-издания
посреди тела), резать которую значит терять реальный текст автора после неё; в этом случае
срез не делается, а сигналится back_suspect. Если front-маркер вообще не разрешился, но есть
блок оглавления (TOC) — это само по себе сигнал аппарата (front_unresolved_toc_present);
tier_records в этом случае не запекает голову-до-конца-TOC как 🔵, даже без точной границы."""
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


_FOOTNOTE_DEF_RE = re.compile(r"^\s*\[\d+\]\s")


def _split_depth(text, depth=0):
    """Ядро split_inline с ПРОТЯГИВАНИЕМ глубины скобок между записями → (segments, end_depth).
    Многострочный коммент [..\\n..\\n..] остаётся 🟢 на всех строках (depth>0 переносится далее).
    Строка-ОПРЕДЕЛЕНИЕ сноски '[n] текст' на верхнем уровне целиком 🟢: текст сноски стоит ВНЕ
    скобок и иначе утёк бы в 🔵 (fail-closed вниз)."""
    if depth == 0 and _FOOTNOTE_DEF_RE.match(text):
        s = text.strip()
        return ([(s, "commentary")] if s else []), 0
    out, buf = [], []

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
        push("commentary" if depth > 0 else "author")
    return out, depth


def split_inline(text):
    """[(segment, role)], role ∈ {author, commentary} для ОДНОЙ строки (depth=0). Тонкая обёртка над
    _split_depth — обратная совместимость (clean-путь, юнит-тесты fail-closed)."""
    segs, _ = _split_depth(text, 0)
    return segs


_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
_CONTENTS_RE = re.compile(r"^\s*(CONTENTS|TABLE\s+OF\s+CONTENTS)\s*$", re.I)


def _contents_span(lines):
    """[start, end) блока оглавления, или None. Оглавление = от строки 'Contents' до разрыва в 2+
    пустых строки (конец списка глав) ИЛИ до первой не-индентированной строки после вхождения
    индентированных пунктов (работает и на stripped-записях без пустых строк). Маркеры ВНУТРИ —
    это пункты оглавления, не реальные заголовки; при выборе границ тела их пропускаем."""
    start = None
    for i, ln in enumerate(lines):
        if _CONTENTS_RE.match(ln):
            start = i
            break
    if start is None:
        return None
    cap = min(len(lines), start + 120)
    blanks = 0
    saw_entry = False   # видели хотя бы один индентированный пункт (= мы в теле TOC)
    for j in range(start + 1, cap):
        ln = lines[j]
        if ln.strip():
            blanks = 0
            if ln[0].isspace():
                saw_entry = True          # индентированный пункт оглавления
            elif saw_entry:
                # первая не-индентированная строка после пунктов → TOC закончился
                return (start, j)
        else:
            blanks += 1
            if blanks >= 2 and j - start > 2:
                return (start, j)
    return (start, cap)


def _resolve_span(lines, front_until=None, back_from=None):
    """TOC-aware, регистронезависимое разрешение границ тела. front_until ВКЛЮЧИТЕЛЬНО: первое
    вхождение маркера ВНЕ блока оглавления. back_from: последнее вхождение ПОСЛЕ начала тела и вне
    оглавления; иначе среза нет (хвост остаётся телом). Возвращает (start, end) индексы строк."""
    toc = _contents_span(lines)

    def in_toc(i):
        return toc is not None and toc[0] <= i < toc[1]

    start, end = 0, len(lines)
    if front_until:
        fl = front_until.lower()
        for i, ln in enumerate(lines):
            if fl in ln.lower() and not in_toc(i):
                start = i
                break
    if back_from:
        bl = back_from.lower()
        for i in range(len(lines) - 1, -1, -1):
            if bl in lines[i].lower() and not in_toc(i) and i > start:
                end = i
                break
    return start, end


def strip_sections(text, front_until=None, back_from=None):
    """Срез фронт/бэк-материи через TOC-aware резолвер: всё ДО строки front_until и ОТ back_from.
    front_until ВКЛЮЧИТЕЛЬНО (строка-маркер остаётся первой строкой тела). None → не резать."""
    lines = text.splitlines()
    start, end = _resolve_span(lines, front_until, back_from)
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


_BACK_TRAIL_FRACTION = 0.70  # срез-кандидат должен лежать в последних ~30% строк файла,
# иначе это, вероятнее всего, ВНУТРЕННЯЯ секция (напр. библиография научного PD-издания
# посреди тела) — резать её значит молча терять реальные слова автора после неё (#55).


def _is_trailing(idx, n):
    """idx (граница среза) — в хвостовых ~30% файла? n=0 → тривиально true (нет строк резать)."""
    return n == 0 or idx >= _BACK_TRAIL_FRACTION * n


def scan(text):
    """Детерминированный отчёт об аппарате. Поле signals — СЛУЖЕБНОЕ (юзеру не показывать).

    Два host-gated усиления (#55, follow-up после апарат-ревью):
    1. back-срез засчитывается уверенным (back_confident) только если кандидат лежит в
       хвостовых ~30% файла (_is_trailing); иначе — back_suspect=True, среза НЕТ (хвост тела
       не режем), но хосту сигналим причину. Так внутренняя ("mid-file") библиография/индекс
       научного издания не срубает реальный текст автора после себя.
    2. если front-маркер вообще не нашёлся (регекс не совпал), но при этом есть блок оглавления
       (TOC) — это само по себе сигнал аппарата: has_apparatus/needs_host_review поднимаются
       с явной причиной front_unresolved_toc_present, а tier_records (ниже) не запекает
       голову-до-конца-TOC как 🔵, даже без точной границы вступления."""
    lines = text.splitlines()
    bracket_ratio = _bracket_ratio(lines)
    commentator_hits = sum(text.count(c) for c in _COMMENTATORS)
    toc = _contents_span(lines)

    def _first_outside(rx):
        for i, ln in enumerate(lines):
            if (toc is None or not (toc[0] <= i < toc[1])) and rx.match(ln):
                return i, ln.strip()
        return None, None

    fi, front_marker = _first_outside(_FRONT_RE)   # реальный заголовок, не пункт оглавления
    bi, back_marker = _first_line(lines, _BACK_RE)  # первое совпадение — кандидат-текст на срез
    start, end = _resolve_span(lines, front_marker, back_marker)
    front_ok = front_marker is not None and start > 3      # тело реально начинается ниже шапки
    back_cut = back_marker is not None and end < len(lines)     # срез вообще нашёлся
    back_trailing = back_cut and _is_trailing(end, len(lines))  # и лежит в хвосте файла
    back_ok = back_trailing                                     # уверенный срез = хвостовой срез
    back_suspect = back_cut and not back_trailing   # найден, но НЕ хвостовой → mid-file, не режем
    front_unresolved_apparatus = front_marker is None and toc is not None
    bracket = bracket_ratio >= 0.25 or commentator_hits >= 5
    has_apparatus = bracket or front_ok or back_ok or back_suspect or front_unresolved_apparatus
    reasons = []
    if back_suspect:
        reasons.append("back_suspect_mid_file")
    if front_unresolved_apparatus:
        reasons.append("front_unresolved_toc_present")
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
            "back_suspect": back_suspect,
            "toc_present": toc is not None,
        },
        "needs_host_review": has_apparatus and not (front_ok and back_ok),
        "review_reasons": reasons,
        "sample_author": sample_auth,
        "sample_apparatus": sample_app,
        "suggested_mode": "tier" if has_apparatus else "raw",
        "inline_commentary": "bracket" if bracket else None,
    }


def tier_records(recs, front_until=None, back_from=None,
                 front_confident=False, back_confident=False, inline="bracket"):
    """recs: [(loc, text)] → [{loc, text, tier}]. Секции-поля: drop если уверенно, иначе S1 (🟢,
    fail-closed). Тело: _split_depth с протяжкой глубины скобок сквозь записи (многострочный
    коммент → 🟢 целиком) → author=P1 (🔵), commentary=S1 (🟢).

    Fail-closed #55(2): если front_until вообще не разрешился (None — регекс не нашёл заголовок),
    но в тексте есть блок оглавления (TOC), голова-до-конца-TOC гарантированно НЕ тело — её сдвигаем
    в front-срез (обычно уйдёт в S1 через front_confident=False), а не отдаём в общий body-тиринг,
    где она без скобок запеклась бы 🔵. На файлах без TOC это ветвь не трогает ничего (no-op)."""
    texts = [t for _, t in recs]
    start, end = _resolve_span(texts, front_until, back_from)
    if front_until is None:
        toc = _contents_span(texts)
        if toc is not None and toc[1] > start:
            start = toc[1]
    out, depth = [], 0
    for i, (loc, text) in enumerate(recs):
        if i < start or i >= end:                     # поле (вступление/приложение)
            confident = front_confident if i < start else back_confident
            if confident:
                continue                              # уверенно аппарат → drop
            out.append({"loc": loc, "text": text, "tier": "S1"})   # неуверенно → 🟢
            continue
        if inline == "bracket":
            segs, depth = _split_depth(text, depth)   # глубина скобок ТЕЧЁТ сквозь тело
            for seg, role in segs:
                out.append({"loc": loc, "text": seg, "tier": "P1" if role == "author" else "S1"})
        else:
            out.append({"loc": loc, "text": text, "tier": "P1"})
    return out
