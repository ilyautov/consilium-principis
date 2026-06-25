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


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _corpus_norm_text(advisor_dir: str):
    """Читает corpus.jsonl и возвращает список (source, norm_chunk) для каждого чанка."""
    path = corpus_path(advisor_dir)
    chunks = []
    if not os.path.isfile(path):
        return chunks
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            text = rec.get("text") or ""
            src = rec.get("source") or rec.get("citation") or "corpus.jsonl"
            chunks.append((str(src), _norm(text)))
    return chunks


def _iter_chunks(advisor_dir):
    path = corpus_path(advisor_dir)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


_TIER_ORDER = {"P1": 0, "P2": 1, "S1": 2, "S2": 3, "B": 4, "A": 5}


def best_match(quote: str, advisor_dir: str):
    """Самый авторитетный дословный матч цитаты: (tier, source) или None.

    Если цитата встречается в нескольких чанках разных тиров (напр. Тарасов-S1
    дословно цитирует Макиавелли, и та же фраза есть в Prince-P1), возвращаем
    пару из ЛУЧШЕГО (самого авторитетного) тира — чтобы source соответствовал
    тиру, который определит маркер. Чанк без поля tier → "A" (fail-closed)."""
    q = _norm(quote)
    if not q:
        return None
    best = None  # (rank, tier, source)
    for ch in _iter_chunks(advisor_dir):
        if q in _norm(ch.get("text", "")):
            t = ch.get("tier", "A")
            rank = _TIER_ORDER.get(t, 9)
            if best is None or rank < best[0]:
                src = ch.get("source") or ch.get("citation") or "corpus.jsonl"
                best = (rank, t, str(src))
    return (best[1], best[2]) if best else None


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
    if not q:
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
