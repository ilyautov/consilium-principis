"""Backend-независимый verbatim-чек: дословна ли цитата в загруженном корпусе advisor'а.
Это ядро защитного контура — работает даже на 0-install полу (нужен только corpus.jsonl)."""
import os
import re
import json
from typing import Optional


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _corpus_norm_text(advisor_dir: str):
    """Склеивает ВЕСЬ corpus.jsonl в один нормализованный текст + карту source.
    Возвращает (joined_norm, list[(source, norm_chunk)])."""
    path = os.path.join(advisor_dir, "corpus.jsonl")
    chunks = []
    if not os.path.isfile(path):
        return "", chunks
    for line in open(path, encoding="utf-8"):
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
    return " ".join(c for _, c in chunks), chunks


def verbatim_in_corpus(quote: str, advisor_dir: str) -> Optional[str]:
    """Возвращает source чанка, где цитата встречается дословно (после нормализации),
    иначе None. Сначала ищет в отдельных чанках (даёт точный source), затем в склейке."""
    q = _norm(quote)
    if not q:
        return None
    _, chunks = _corpus_norm_text(advisor_dir)
    for src, ctext in chunks:
        if q in ctext:
            return src
    joined = " ".join(c for _, c in chunks)
    return "corpus.jsonl" if q in joined else None
