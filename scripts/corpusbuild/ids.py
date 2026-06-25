"""Стабильные идентификаторы узлов графа и загрузка корпуса."""
import json
from . import paths


def chunk_id(rec: dict) -> str:
    """Детерминированный id чанка = source:startline-endline."""
    return f'{rec["source"]}:{rec["start"][1]}-{rec["end"][1]}'


def load_corpus(advisor_dir: str) -> list:
    """Читает build/corpus.jsonl, добавляет каждому записи поле 'id'."""
    out = []
    with open(paths.corpus_path(advisor_dir), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                rec["id"] = chunk_id(rec)
                out.append(rec)
    return out
