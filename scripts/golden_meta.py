#!/usr/bin/env python3
"""§1.4 moat-v2: версионирование golden ↔ корпус.

Дыра: пересборка корпуса смещает чанки — якоря golden молча протухают, и eval меряет
метрики против корпуса, которого больше нет. Фикс: продюсеры golden-jsonl пишут ПЕРВОЙ
строкой meta-запись {"_meta": {"corpus_sha12": ...}} с content-хэшем corpus.jsonl на
момент генерации; лоадеры eval сравнивают с текущим хэшем и при мисматче ГРОМКО
предупреждают в stderr (не падение — числа всё ещё считаются, но интерпретировать
с осторожностью). Легаси-файлы без meta грузятся молча, как раньше (бэк-компат).
Файлы scripts/golden/ гитигнорятся — версионируется ТУЛИНГ, не данные.
"""
import os
import sys
import json
import hashlib
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from corpusbuild.paths import corpus_path

HASH_LEN = 12


def corpus_sha12(advisor_dir):
    """sha256 содержимого corpus.jsonl советника, первые 12 hex. Нет корпуса/ошибка → None."""
    try:
        cp = corpus_path(advisor_dir)
        if not os.path.isfile(cp):
            return None
        h = hashlib.sha256()
        with open(cp, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()[:HASH_LEN]
    except Exception:
        return None


def meta_record(advisor_dir):
    """Meta-строка для головы golden-файла или None (нет корпуса → нечего фиксировать)."""
    sha = corpus_sha12(advisor_dir)
    if not sha:
        return None
    return {"_meta": {"corpus_sha12": sha,
                      "advisor": os.path.basename(str(advisor_dir).rstrip("/")),
                      "generated": datetime.date.today().isoformat()}}


def split_meta(rows):
    """(meta|None, data_rows): отделяет первую _meta-запись от данных. Легаси → (None, rows)."""
    meta, data = None, []
    for r in rows or []:
        if meta is None and isinstance(r, dict) and "_meta" in r:
            m = r["_meta"]
            meta = m if isinstance(m, dict) else {}
        else:
            data.append(r)
    return meta, data


def warn_on_drift(meta, advisor_dir, path=""):
    """True + ГРОМКОЕ предупреждение в stderr, если корпус уехал от зафиксированного в golden.
    Не падение: числа считаются, но якоря могли протухнуть. Легаси (meta=None) → молча False."""
    if not isinstance(meta, dict):
        return False
    want = meta.get("corpus_sha12")
    if not want:
        return False
    cur = corpus_sha12(advisor_dir)
    if cur is None or cur == want:
        return False
    print(
        "\n"
        "⚠️ ═══════════════════════ GOLDEN↔CORPUS DRIFT ═══════════════════════ ⚠️\n"
        f"⚠️  {path or 'golden-файл'}: генерировался на корпусе {want},\n"
        f"⚠️  текущий корпус {advisor_dir} = {cur}. Чанки могли сместиться —\n"
        "⚠️  якоря golden протухли, метрики интерпретируй с осторожностью.\n"
        "⚠️  Пересобери golden (gen_golden/synth_eval) на текущем корпусе.\n"
        "⚠️ ════════════════════════════════════════════════════════════════════ ⚠️",
        file=sys.stderr)
    return True
