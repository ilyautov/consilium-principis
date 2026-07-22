"""build.lock.json — воспроизводимость: хеши источников + config + счётчики тиров + gov_head.
built_at передаётся аргументом (в скриптах нет argless-времени для детерминизма)."""
import os, sys, hashlib
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # corpusbuild/ → scripts/
from file_atomic import atomic_write_json
from . import paths


def _gov_head(chunks):
    """Governance-голова: отпечаток корпуса (hash-chain) на момент сборки. Сохраняется в lock,
    чтобы governance.verify ловил ПОДМЕНУ corpus.jsonl ПОСЛЕ факта (раньше цепь сверялась сама
    с собой = тавтология). chunks здесь — те же записи, что пишутся в corpus.jsonl."""
    from governance import build_chain, GENESIS
    chain = build_chain(list(chunks))
    return chain[-1]["hash"] if chain else GENESIS


def _hash_file(path: str) -> str:
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    return f"sha256:{h}"


def write_lock(advisor_dir: str, config: dict, chunks, built_at: str, *, output_path=None,
               register_head=True) -> dict:
    src_dir = os.path.join(advisor_dir, "sources")
    sources = {}
    if os.path.isdir(src_dir):
        for fn in sorted(os.listdir(src_dir)):
            fp = os.path.join(src_dir, fn)
            if os.path.isfile(fp) and not fn.endswith(".json"):
                sources[fn] = _hash_file(fp)
    counts = dict(Counter(c["tier"] for c in chunks))
    counts["chunks"] = len(chunks)
    # tiering_version: тир запечён В КОРПУС при сборке — код тиринга чинили 5 раз, и ни одна
    # починка не доехала до уже собранных корпусов, потому что заметить было нечем (чанк несёт
    # только текст+тир). Штамп → doctor.check_corpus_tiering видит стухание и требует пересборки.
    from .apparatus import TIERING_VERSION
    lock = {"built_at": built_at, "tiering_version": TIERING_VERSION, "config": config,
            "sources": sources, "counts": counts, "gov_head": _gov_head(chunks)}
    atomic_write_json(output_path or paths.lock_path(advisor_dir), lock,
                      ensure_ascii=False, indent=2)
    # Якорь ВНЕ подменяемой папки: легитимная сборка регистрирует голову в gov_heads.json
    # (корень доски) — verify_advisor ловит подмену советника ЦЕЛИКОМ (самосогласованный
    # двойник несёт свои lock'и, но якорь унести не может). Советник вне корня → no-op.
    if register_head:
        from governance import register_head
        register_head(advisor_dir, lock["gov_head"], n=len(chunks))
    return lock
