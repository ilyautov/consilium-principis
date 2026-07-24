# -*- coding: utf-8 -*-
"""
tier_full.py — семантический FULL-тир (ollama + bge-m3) под «личный совет директоров».

Контракт (его ждёт scripts/eval.py — НЕ менять сигнатуры):
    available() -> bool
    build_index(advisor_dir: str) -> None
    retrieve(question, advisor_dir, top_k=3) -> list[dict]
        каждый dict: {"text": str, "score": float, "source": str}

САМОДОСТАТОЧНОСТЬ: внешнего движка НЕ требует. Эмбеддинг-примитив (embed_batch) вшит —
батчевый bge-m3 через ollama /api/embed (нормировка |v|=1), и для индексации корпуса, и
для эмбеддинга вопроса при retrieve. Косинусная математика retrieve (Mn @ qv по
нормированным векторам) поверх нашего корпуса (advisors/<name>/corpus.jsonl).

ГДЕ ЛЕЖАТ ЭМБЕДДИНГИ: <project>/data/embeddings_<advisor>.npy (+ data/embeddings_<advisor>.meta.json).
Имя матчит существующий паттерн .gitignore `data/embeddings*.npy` → не коммитятся.
Производное от чужих текстов остаётся локальным (легальная граница).
"""
import os
import re
import sys
import json
import hashlib
import threading
import urllib.request

import numpy as np

from corpusbuild.paths import corpus_path
from engine import provenance, corpus_sha256, StaleIndexError

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# Версия ФОРМАТА индекса (нормировка матрицы / раскладка меты). Аналог apparatus.TIERING_VERSION:
# бампни, если сменилась математика/формат матрицы — старые .npy инвалидируются fingerprint'ом
# даже при неизменных корпусе/модели/чанкинге. Владелец константы = автор формата индекса.
INDEX_VERSION = 1


# Кэп одновременных embed-запросов к ЕДИНОМУ локальному ollama. Веер совета (5-10 параллельных
# cite) без кэпа = thundering herd: на холодной модели первый грузит bge-m3 под нехваткой памяти
# (конкуренция с большими чат-моделями), остальные встают в очередь и рвут 60с MCP-таймаут. Кэп
# сериализует: первый прогревает модель, следующие переиспользуют тёплую. Env-настройка.
_EMBED_SEMAPHORE = threading.BoundedSemaphore(int(os.getenv("EMBED_MAX_CONCURRENCY", "2")))


def embed_batch(texts):
    """Батч-эмбеддинг через ollama /api/embed (bge-m3) — ВШИТЫЙ примитив (тот же эндпоинт и
    нормировка, что прежде брались из внешнего RAG-движка). FULL-тиру достаточно ollama, внешний
    репо не нужен. Возвращает list[list[float]]; нормировку |v|=1 делает вызывающий.

    Робастность на нагруженной машине: (1) keep_alive пинит bge-m3 в памяти между запросами, иначе
    ollama вытесняет модель под давлением больших чат-моделей и следующий запрос холодно грузится
    > 60с (наблюдалось на дев-машине с gemma3:27b); (2) _EMBED_SEMAPHORE ограничивает одновременные
    запросы к единому ollama (см. константу выше)."""
    texts = list(texts)
    if not texts:
        return []
    payload = {"model": EMBED_MODEL, "input": texts,
               "keep_alive": os.getenv("EMBED_KEEP_ALIVE", "30m")}     # пин модели в памяти
    req = urllib.request.Request(
        f"{OLLAMA}/api/embed",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with _EMBED_SEMAPHORE:                                             # сериализация против herd
        with urllib.request.urlopen(req, timeout=int(os.getenv("EMBED_TIMEOUT", "120"))) as r:
            embs = json.loads(r.read()).get("embeddings")
    if not embs or len(embs) != len(texts):
        raise RuntimeError(f"ollama /api/embed: {len(embs or [])} векторов на {len(texts)} входов")
    return embs

# Корень проекта и каталог эмбеддингов (имя матчит .gitignore: data/embeddings*.npy).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


# ---------------------------------------------------------------- health-check
def available() -> bool:
    """True, если ollama жив И bge-m3 отвечает на эмбеддинг (быстрый health-check с таймаутом).
    Делает один короткий /api/embed на пробном тексте — тем же путём, что и индексатор корпуса."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA}/api/embed",
            data=json.dumps({"model": EMBED_MODEL, "input": ["ping"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            emb = json.loads(r.read()).get("embeddings")
        return bool(emb) and len(emb) == 1 and len(emb[0]) > 0
    except Exception:
        return False


# ------------------------------------------------------------------- chunking
def _read_corpus_chunks(advisor_dir: str, corpus_file=None):
    """Читает advisors/<name>/corpus.jsonl и режет на осмысленные пассажи.

    Наш корпус может хранить весь отрывок одной строкой (одна большая `text`) — для
    осмысленного top-3 и дискриминативного score режем длинный text по предложениям
    в пассажи. Каждый пассаж сохраняет source (citation) из исходного чанка.

    Дефолт chunk_chars=500 — согласован с калибровкой abstain_threshold (semantic 0.50)
    в board_config.json на реальном корпусе. Меньший чанк требует пере-калибровки порога."""
    chunk_chars = int(os.getenv("TIER_CHUNK_CHARS", "500"))
    path = corpus_file or corpus_path(advisor_dir)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"нет корпуса: {path}")

    passages = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        text = (rec.get("text") or "").strip()
        if not text:
            continue
        source = rec.get("source") or rec.get("citation") or os.path.basename(advisor_dir)
        tier = rec.get("tier") or provenance.tier_for(rec.get("source", ""), 0, advisor_dir)
        # режем на предложения и группируем в пассажи ~ до chunk_chars символов
        sents = re.split(r"(?<=[.!?])\s+", text)
        buf = ""
        for s in sents:
            s = s.strip()
            if not s:
                continue
            if buf and len(buf) + len(s) + 1 > chunk_chars:
                passages.append({"text": buf.strip(), "source": str(source), "tier": tier})
                buf = s
            else:
                buf = (buf + " " + s).strip()
        if buf:
            passages.append({"text": buf.strip(), "source": str(source), "tier": tier})
    if not passages:
        raise ValueError(f"корпус пуст после чанкинга: {path}")
    return passages


def _legacy_paths(advisor_dir: str):
    name = os.path.basename(advisor_dir.rstrip("/")) or "advisor"
    os.makedirs(DATA_DIR, exist_ok=True)
    emb = os.path.join(DATA_DIR, f"embeddings_{name}.npy")
    meta = os.path.join(DATA_DIR, f"embeddings_{name}.meta.json")
    return emb, meta


def _paths(advisor_dir: str):
    """Paths inside one active snapshot; data/ remains the pre-generation fallback."""
    from corpusbuild import pipeline
    generation = pipeline.active_generation_dir(advisor_dir)
    if generation:
        return (os.path.join(generation, "embeddings.npy"),
                os.path.join(generation, "embeddings.meta.json"))
    return _legacy_paths(advisor_dir)


# -------------------------------------------------------------- fingerprint (staleness)
def _effective_chunk_chars() -> int:
    """chunk_chars, которым РЕАЛЬНО режет _read_corpus_chunks (env override над дефолтом 500).
    Источник правды для fingerprint = фактическая нарезка индекса, не декларация в конфиге
    (семантический чанкер board_config.chunk_chars не читает — см. спека §4 в.1)."""
    return int(os.getenv("TIER_CHUNK_CHARS", "500"))


def _corpus_digest(path: str):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _index_fingerprint(advisor_dir: str, corpus_file=None) -> dict:
    """Отпечаток, связывающий индекс с {корпус, модель, чанкинг, формат}. Зеркало staleness
    load_calibration: рассинхрон ЛЮБОГО поля = индекс устарел (fail-closed). corpus_sha256 —
    ЕДИНЫЙ хэшер (engine.corpus_sha256, не форкать)."""
    return {
        "corpus_sha256": _corpus_digest(corpus_file) if corpus_file else corpus_sha256(advisor_dir),
        "embed_model": EMBED_MODEL,
        "chunk_chars": _effective_chunk_chars(),
        "index_version": INDEX_VERSION,
    }


def _fingerprint_matches(meta: dict, advisor_dir: str, corpus_file=None) -> bool:
    """True только при полном совпадении сохранённого fingerprint с текущим. Легаси-мета без
    поля 'fingerprint' → False (fail-closed, как калибровка без corpus_sha256)."""
    stored = (meta or {}).get("fingerprint")
    if not isinstance(stored, dict):
        return False
    return stored == _index_fingerprint(advisor_dir, corpus_file=corpus_file)


# --------------------------------------------------------------- build_index
def _write_index(passages, emb_path: str, meta_path: str, fingerprint: dict) -> None:
    """Write only into a private staging directory (or legacy data/ fallback)."""
    batch = int(os.getenv("EMBED_BATCH", "64"))
    vecs = []
    for i in range(0, len(passages), batch):
        chunk_texts = [p["text"] for p in passages[i:i + batch]]
        vecs.extend(embed_batch(chunk_texts))
    matrix = np.asarray(vecs, dtype=np.float32)
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    with open(emb_path, "wb") as handle:
        np.save(handle, matrix)
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump({"fingerprint": fingerprint, "model": EMBED_MODEL, "passages": passages},
                  handle, ensure_ascii=False)


def _reader_snapshot(advisor_dir: str):
    """Resolve corpus and index paths once so a pointer switch cannot mix generations."""
    from corpusbuild import pipeline
    generation = pipeline.active_generation_dir(advisor_dir)
    if generation:
        return (os.path.join(generation, "corpus.jsonl"),
                os.path.join(generation, "embeddings.npy"),
                os.path.join(generation, "embeddings.meta.json"))
    # Keep the historical _paths seam for legacy integrations and tests.
    emb_path, meta_path = _paths(advisor_dir)
    legacy_corpus = corpus_path(advisor_dir)
    return (legacy_corpus if os.path.isfile(legacy_corpus) else None), emb_path, meta_path


def build_index(advisor_dir: str) -> None:
    """Строит семантический индекс для advisors/<name>/corpus.jsonl вшитым embed_batch
    (батч bge-m3 через ollama). Сохраняет нормированную матрицу в data/embeddings_<name>.npy
    и пассажи (text/source) в .meta.json."""
    from corpusbuild import pipeline
    with pipeline.publisher_lock(advisor_dir):
        stage, token = pipeline.stage_generation(advisor_dir)
        corpus_file = os.path.join(stage, "corpus.jsonl")
        try:
            passages = _read_corpus_chunks(advisor_dir, corpus_file=corpus_file)
            _write_index(passages, os.path.join(stage, "embeddings.npy"),
                         os.path.join(stage, "embeddings.meta.json"),
                         _index_fingerprint(advisor_dir, corpus_file=corpus_file))
            pipeline.publish_generation(advisor_dir, stage, token)
        except BaseException:
            pipeline.discard_staging(stage)
            raise


# ------------------------------------------------------------------ retrieve
def _embed_query(question: str) -> np.ndarray:
    """Эмбеддинг вопроса тем же вшитым embed_batch, нормированный — чтобы Mn @ qv был
    чистым косинусом и порог abstain_threshold был осмыслен."""
    qv = np.asarray(embed_batch([question])[0], dtype=np.float32)
    return qv / (np.linalg.norm(qv) + 1e-9)


def index_ready(advisor_dir: str) -> bool:
    """Дёшево: индекс существует И fingerprint совпал — БЕЗ сборки и БЕЗ эмбеддинга.
    Нужен hot-path'у (engine.retrieval), чтобы НЕ триггерить инлайн build_index в ответе на
    запрос: на большом корпусе (Тиньков ~2000 чанков) сборка > 60с рвёт таймаут MCP-транспорта
    (живой инцидент 2026-07-24, «нет опоры»). retrieve() ниже по-прежнему авто-лечит индекс для
    прямых/CLI-вызовов (контракт generation-publication) — гейт только для прод-ретрива."""
    corpus_file, emb_path, meta_path = _reader_snapshot(advisor_dir)
    if not (os.path.isfile(emb_path) and os.path.isfile(meta_path)):
        return False
    try:
        meta = json.load(open(meta_path, encoding="utf-8"))
    except Exception:
        return False
    return _fingerprint_matches(meta, advisor_dir, corpus_file=corpus_file)


def retrieve(question: str, advisor_dir: str, top_k: int = 3):
    """Возвращает top_k пассажей: [{"text","score","source"}].
    score = косинус bge-m3 поверх нашего корпуса (Mn @ qv по нормированным векторам)."""
    corpus_file, emb_path, meta_path = _reader_snapshot(advisor_dir)
    if not (os.path.isfile(emb_path) and os.path.isfile(meta_path)):
        build_index(advisor_dir)
        # build_index publishes a new immutable generation; retain no paths from the
        # previous snapshot.
        corpus_file, emb_path, meta_path = _reader_snapshot(advisor_dir)

    meta = json.load(open(meta_path, encoding="utf-8"))
    # Fail-closed staleness (спека 2026-07-18 §1.3, Вариант B): устаревший индекс НЕ используем.
    # Не авто-rebuild в hot-path — поднимаем StaleIndexError; safe_retrieve деградирует на lexical
    # (наблюдаемо), явная пересборка живёт в pipeline/doctor. Легаси-мета без fingerprint → stale.
    if not _fingerprint_matches(meta, advisor_dir, corpus_file=corpus_file):
        raise StaleIndexError(
            f"семантический индекс '{os.path.basename(advisor_dir.rstrip('/'))}' устарел: "
            "fingerprint (corpus_sha256/embed_model/chunk_chars/index_version) не совпал с текущим "
            "корпусом/конфигом. Пересобери: pipeline.build / doctor / build_index. "
            "safe_retrieve сейчас деградирует на лексический пол.")
    M = np.load(emb_path).astype(np.float32)
    passages = meta["passages"]
    M = M[:len(passages)]

    qv = _embed_query(question)
    sims = M @ qv  # косинус (M и qv нормированы)

    idx = sims.argsort()[::-1][:top_k]
    return [
        {"text": passages[i]["text"], "score": float(sims[i]),
         "source": passages[i]["source"], "tier": passages[i].get("tier")}
        for i in idx
    ]


# ------------------------------------------------------------------- self-test
if __name__ == "__main__":
    adv = sys.argv[1] if len(sys.argv) > 1 else "advisors/marcus-aurelius"
    if not os.path.isabs(adv):
        adv = os.path.join(PROJECT_ROOT, adv)
    print("available:", available())
    build_index(adv)
    q = "How do I handle being pulled in too many directions and too many projects?"
    for d in retrieve(q, adv, top_k=3):
        print(f"  {d['score']:+.4f}  [{d['source']}]  {d['text'][:80]}")
