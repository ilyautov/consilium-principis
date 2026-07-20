"""Backend-независимый verbatim-чек: дословна ли цитата в загруженном корпусе advisor'а.
Это ядро защитного контура — работает даже на 0-install полу (нужен только corpus.jsonl)."""
import os
import re
import json
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from corpusbuild.paths import corpus_path
from typing import Optional


# 🔵/🟢 требует осмысленного фрагмента (H2, Правило A): порог — по СЛОВАМ, не символам.
# Одиночное/двухсловное совпадение («remember», «your mortality») дословно найдётся, но
# как «цитата» бессмысленно и вводит в заблуждение. Ниже MIN_QUOTE_WORDS → None (🟡, fail-closed).
MIN_QUOTE_WORDS = 3
# MIN_QUOTE_CHARS сохранён для внешнего использования (citation_rate_eval: мин. длина
# извлекаемого кавычного спана) — это ОТДЕЛЬНАЯ ось, гейтом верности больше не служит.
MIN_QUOTE_CHARS = 8

# Токены-отрицания (C1+C2): обрезка, отсекающая ведущее отрицание, переворачивает смысл
# цитаты. «t» — хвост контракций после _norm («don't»→«don t»); «nt» оставлен бэк-компатно.
_NEG = {"not", "no", "never", "nt", "t", "cannot", "without", "nor",
        "не", "ни", "нет", "никогда", "никто", "нельзя", "без", "вовсе"}

# Разделители предложений: скоуп гарда — предложение (см. ниже).
_SENT_SPLIT = re.compile(r"[.!?…;:\n»«\"“”]+")


def _crop_severs_negation(q: str, raw_text: str) -> bool:
    """True, если обрезка отсекла отрицание из исходного ПРЕДЛОЖЕНИЯ (C2).

    _norm стирает пунктуацию, поэтому гард по окну токенов двойно ошибался: пропускал
    дистанционное «did not in any real sense believe…» (ложный 🔵) и топил бы цитаты
    из-за «not» в СОСЕДНЕМ предложении (ложный 🟡). Режем СЫРОЙ текст на предложения,
    каждое нормализуем; префикс q внутри его предложения сканируем ЦЕЛИКОМ по _NEG.
    Есть хотя бы одно чистое вхождение → False (🔵 легитимен). q через шов предложений
    (не найден ни в одном) → False: это честная дословная подстрока by design.
    Оба аргумента: q норм. (_norm), raw_text — НЕнормализованный."""
    found = False
    for sent in _SENT_SPLIT.split(raw_text or ""):
        ns = _norm(sent)
        i = ns.find(q) if ns else -1
        if i < 0:
            continue
        found = True
        if not any(tok in _NEG for tok in ns[:i].split()):
            return False                       # чистое вхождение без отрицания в префиксе
    return found                               # все вхождения с отрицанием → обрезка


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


# C5/H10: нормализация чанков корпуса кешируется по (path, mtime). best_match зовётся на
# ~56 кандидатов за сессию — без кеша это полный ре-парс+ре-норм corpus.jsonl на КАЖДЫЙ.
# Инвалидация — сменой mtime (пересборка корпуса меняет файл): fail-safe, не stale.
# Записи с прежним mtime того же пути вытесняются → кеш не растёт неограниченно.
_CHUNK_CACHE = {}   # (path, mtime) -> list[dict]  (raw-запись + служебный "_norm")


def _load_chunks(advisor_dir: str):
    """Список raw-записей corpus.jsonl (кешируется по mtime). У каждой добавлен служебный
    ключ "_norm" — нормализованный текст (посчитан один раз, переиспользуется best_match /
    _corpus_norm_text). Нет файла → []."""
    path = corpus_path(advisor_dir)
    if not os.path.isfile(path):
        return []
    key = (path, os.path.getmtime(path))
    hit = _CHUNK_CACHE.get(key)
    if hit is not None:
        return hit
    chunks = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            rec["_norm"] = _norm(rec.get("text") or "")
            chunks.append(rec)
    for k in [k for k in _CHUNK_CACHE if k[0] == path and k != key]:
        del _CHUNK_CACHE[k]                              # вытесняем прежний mtime того же пути
    _CHUNK_CACHE[key] = chunks
    return chunks


def _corpus_norm_text(advisor_dir: str):
    """Список (source, norm_chunk) для каждого чанка — из кеша _load_chunks."""
    return [(str(rec.get("source") or rec.get("citation") or "corpus.jsonl"), rec["_norm"])
            for rec in _load_chunks(advisor_dir)]


def _iter_chunks(advisor_dir):
    return _load_chunks(advisor_dir)


_TIER_ORDER = {"P1": 0, "P2": 1, "S1": 2, "S2": 3, "B": 4, "A": 5}


def best_match(quote: str, advisor_dir: str):
    """Самый авторитетный дословный матч цитаты: (tier, source) или None.

    Если цитата встречается в нескольких чанках разных тиров (напр. Тарасов-S1
    дословно цитирует Макиавелли, и та же фраза есть в Prince-P1), возвращаем
    пару из ЛУЧШЕГО (самого авторитетного) тира — чтобы source соответствовал
    тиру, который определит маркер. Чанк без поля tier → "A" (fail-closed)."""
    q = _norm(quote)
    if len(q.split()) < MIN_QUOTE_WORDS:                 # <3 слов → не 🔵 (H2, fail-closed)
        return None
    best = None  # (rank, tier, source)
    for ch in _load_chunks(advisor_dir):
        if q in ch["_norm"] and not _crop_severs_negation(q, ch.get("text") or ""):
            t = ch.get("tier", "A")
            rank = _TIER_ORDER.get(t, 9)
            if best is None or rank < best[0]:
                src = ch.get("source") or ch.get("citation") or "corpus.jsonl"
                best = (rank, t, str(src))
    return (best[1], best[2]) if best else None


def marker_status(quote: str, advisor_dir: str) -> dict:
    """ЕДИНЫЙ источник маркера по тиру дословного матча (H6). Оба вызова-обёртки
    (mcp_server._fidelity_check, Engine.fidelity_check) делегируют сюда — одна формула,
    нет дрейфа. P1/P2 → 🔵 (слова автора); S1/S2 → 🟢 (дословно, но комментарий);
    нет матча / B/A / без tier → 🟡 (fail-closed: без провенанса не сертифицируем)."""
    m = best_match(quote, advisor_dir)
    if not m:
        return {"status": "🟡", "verbatim": False, "source": ""}
    tier, src = m
    if tier in ("P1", "P2"):
        return {"status": "🔵", "verbatim": True, "source": src}
    if tier in ("S1", "S2"):
        return {"status": "🟢", "verbatim": True, "source": src}
    return {"status": "🟡", "verbatim": False, "source": ""}


def tier_of_match(quote: str, advisor_dir: str):
    """Тир чанка, где дословно (по нормализации) найдена цитата; None если нигде.
    Приоритет P1/P2 — если матч в нескольких тирах, возвращаем самый авторитетный."""
    m = best_match(quote, advisor_dir)
    return m[0] if m else None


def is_blue_eligible(quote: str, advisor_dir: str) -> bool:
    """🔵 (голосом советника) допустимо только при дословном матче в P1/P2."""
    return tier_of_match(quote, advisor_dir) in ("P1", "P2")


def verbatim_in_corpus(quote: str, advisor_dir: str) -> Optional[str]:
    """Возвращает source чанка, где цитата встречается дословно (после нормализации),
    иначе None.

    Сопоставление — нормализованная подстрока по отдельным чанкам. Цитата, не найденная
    ни в одном чанке, возвращает None (🟡) — кросс-чанковый join не используется,
    чтобы исключить ложные 🔵."""
    q = _norm(quote)
    if len(q.split()) < MIN_QUOTE_WORDS:                 # <3 слов не считаем верифицированной цитатой (H2)
        return None
    chunks = _corpus_norm_text(advisor_dir)
    for src, ctext in chunks:
        if q in ctext:
            return src
    return None


def marker_for_path(path, advisor_dir: str = None) -> str:
    """Маркер составного ответа = слабейшее звено на его трассе по графу (L2.2).
    Нижний слой 🔵 остаётся вербатим-гейтом (is_blue_eligible)."""
    from corpusbuild import graph
    return graph.weakest_link(path)
