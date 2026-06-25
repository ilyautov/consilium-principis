"""build.lock.json — воспроизводимость: хеши источников + config + счётчики тиров.
built_at передаётся аргументом (в скриптах нет argless-времени для детерминизма)."""
import os, json, hashlib
from collections import Counter
from . import paths


def _hash_file(path: str) -> str:
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    return f"sha256:{h}"


def write_lock(advisor_dir: str, config: dict, chunks, built_at: str) -> dict:
    src_dir = os.path.join(advisor_dir, "sources")
    sources = {}
    if os.path.isdir(src_dir):
        for fn in sorted(os.listdir(src_dir)):
            fp = os.path.join(src_dir, fn)
            if os.path.isfile(fp) and not fn.endswith(".json"):
                sources[fn] = _hash_file(fp)
    counts = dict(Counter(c["tier"] for c in chunks))
    counts["chunks"] = len(chunks)
    lock = {"built_at": built_at, "config": config, "sources": sources, "counts": counts}
    os.makedirs(paths.build_dir(advisor_dir), exist_ok=True)
    with open(paths.lock_path(advisor_dir), "w", encoding="utf-8") as f:
        json.dump(lock, f, ensure_ascii=False, indent=2)
    return lock
