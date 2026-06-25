"""Единый резолвер путей корпуса. Все читатели ходят сюда, чтобы build/-реорг
не разъехался по 7 файлам. corpus_path: предпочитает build/, падает на легаси."""
import os


def build_dir(advisor_dir: str) -> str:
    return os.path.join(advisor_dir, "build")


def lock_path(advisor_dir: str) -> str:
    return os.path.join(build_dir(advisor_dir), "build.lock.json")


def corpus_path(advisor_dir: str) -> str:
    """build/corpus.jsonl, если он есть; иначе легаси advisors/<slug>/corpus.jsonl,
    если есть; иначе дефолт build/corpus.jsonl (для свежей сборки)."""
    new = os.path.join(build_dir(advisor_dir), "corpus.jsonl")
    legacy = os.path.join(advisor_dir, "corpus.jsonl")
    if os.path.isfile(new):
        return new
    if os.path.isfile(legacy):
        return legacy
    return new
