# -*- coding: utf-8 -*-
"""
tier_full.py — ТОНКИЙ адаптер движка «Гефест» (rag-sds) под «личный совет директоров».

Контракт (его ждёт scripts/eval.py — НЕ менять сигнатуры):
    available() -> bool
    build_index(advisor_dir: str) -> None
    retrieve(question, advisor_dir, top_k=3, rerank=False) -> list[dict]
        каждый dict: {"text": str, "score": float, "source": str}

ПРИНЦИП: логику Гефеста НЕ переписываем — переиспользуем его модули как зависимость:
  • build_semantic_index.embed_batch — батчевый bge-m3 эмбеддинг через /api/embed
    (тот же эндпоинт, та же нормировка |v|=1, что и в индексаторе Гефеста). Используется
    и для индексации корпуса, и для эмбеддинга вопроса при retrieve.
  • reranker_model.CrossEncoderReranker — кросс-энкодер bge-reranker-v2-m3 (rerank=True).
Косинусная математика retrieve мирроринг SemanticRetriever.query Гефеста (Mn @ qv по
нормированным векторам), но без его hardwired-загрузки corpus_full.json/substances/plants —
у нас другой корпус (advisors/<name>/corpus.jsonl), поэтому переиспользуем эмбеддинг-примитив,
а не класс целиком (см. «несовпадения API» в отчёте).

ГДЕ ЛЕЖАТ ЭМБЕДДИНГИ: <project>/data/embeddings_<advisor>.npy (+ data/embeddings_<advisor>.meta.json).
Имя матчит существующий паттерн .gitignore `data/embeddings*.npy` → не коммитятся.
Производное от чужих текстов остаётся локальным (легальная граница).
"""
import os
import re
import sys
import json
import urllib.request

import numpy as np

# --- подключаем движок Гефеста как внешнюю зависимость (read-only reuse) ---
ENGINE_DIR = os.getenv("HEPHAESTUS_ENGINE", "/Users/USER/personal/pilots/rag-sds/engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import build_semantic_index as bsi  # noqa: E402  — embed_batch (батч bge-m3 /api/embed)

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# Корень проекта и каталог эмбеддингов (имя матчит .gitignore: data/embeddings*.npy).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


# ---------------------------------------------------------------- health-check
def available() -> bool:
    """True, если ollama жив И bge-m3 отвечает на эмбеддинг (быстрый health-check с таймаутом).
    Делает один короткий /api/embed на пробном тексте — тем же путём, что индексатор Гефеста."""
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
def _read_corpus_chunks(advisor_dir: str):
    """Читает advisors/<name>/corpus.jsonl и режет на осмысленные пассажи.

    Наш корпус может хранить весь отрывок одной строкой (одна большая `text`) — для
    осмысленного top-3 и дискриминативного score режем длинный text по предложениям
    в пассажи. Каждый пассаж сохраняет source (citation) из исходного чанка.

    Дефолт chunk_chars=500 — согласован с калибровкой abstain_threshold (semantic 0.50)
    в board_config.json на реальном корпусе. Меньший чанк требует пере-калибровки порога."""
    chunk_chars = int(os.getenv("TIER_CHUNK_CHARS", "500"))
    path = os.path.join(advisor_dir, "corpus.jsonl")
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
        # режем на предложения и группируем в пассажи ~ до chunk_chars символов
        sents = re.split(r"(?<=[.!?])\s+", text)
        buf = ""
        for s in sents:
            s = s.strip()
            if not s:
                continue
            if buf and len(buf) + len(s) + 1 > chunk_chars:
                passages.append({"text": buf.strip(), "source": str(source)})
                buf = s
            else:
                buf = (buf + " " + s).strip()
        if buf:
            passages.append({"text": buf.strip(), "source": str(source)})
    if not passages:
        raise ValueError(f"корпус пуст после чанкинга: {path}")
    return passages


def _paths(advisor_dir: str):
    name = os.path.basename(advisor_dir.rstrip("/")) or "advisor"
    os.makedirs(DATA_DIR, exist_ok=True)
    emb = os.path.join(DATA_DIR, f"embeddings_{name}.npy")
    meta = os.path.join(DATA_DIR, f"embeddings_{name}.meta.json")
    return emb, meta


# --------------------------------------------------------------- build_index
def build_index(advisor_dir: str) -> None:
    """Строит семантический индекс для advisors/<name>/corpus.jsonl, переиспользуя
    build_semantic_index.embed_batch (батч bge-m3). Сохраняет нормированную матрицу в
    data/embeddings_<name>.npy и пассажи (text/source) в .meta.json."""
    passages = _read_corpus_chunks(advisor_dir)
    emb_path, meta_path = _paths(advisor_dir)

    # реюз эмбеддинг-примитива Гефеста: батчи через /api/embed (вектора нормированные).
    batch = int(os.getenv("EMBED_BATCH", "64"))
    vecs = []
    for i in range(0, len(passages), batch):
        chunk_texts = [p["text"] for p in passages[i:i + batch]]
        vecs.extend(bsi.embed_batch(chunk_texts))  # ← движок Гефеста, не наша реализация
    M = np.asarray(vecs, dtype=np.float32)
    # на всякий случай нормируем (embed_batch уже отдаёт |v|=1, но не зависим от этого).
    M = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)

    np.save(emb_path, M)
    json.dump(
        {"model": EMBED_MODEL, "passages": passages},
        open(meta_path, "w", encoding="utf-8"),
        ensure_ascii=False,
    )


# ------------------------------------------------------------------ retrieve
def _embed_query(question: str) -> np.ndarray:
    """Эмбеддинг вопроса тем же примитивом Гефеста (embed_batch), нормированный —
    чтобы Mn @ qv был чистым косинусом и порог abstain_threshold=0.62 был осмыслен."""
    qv = np.asarray(bsi.embed_batch([question])[0], dtype=np.float32)
    return qv / (np.linalg.norm(qv) + 1e-9)


def retrieve(question: str, advisor_dir: str, top_k: int = 3, rerank: bool = False):
    """Возвращает top_k пассажей: [{"text","score","source"}].
    score = косинус bge-m3 (или скор кросс-энкодера при rerank=True).

    Мирроринг косинусной логики SemanticRetriever.query Гефеста (Mn @ qv), но поверх
    нашего корпуса. rerank=True → реюз reranker_model.CrossEncoderReranker."""
    emb_path, meta_path = _paths(advisor_dir)
    if not (os.path.isfile(emb_path) and os.path.isfile(meta_path)):
        build_index(advisor_dir)

    M = np.load(emb_path).astype(np.float32)
    meta = json.load(open(meta_path, encoding="utf-8"))
    passages = meta["passages"]
    M = M[:len(passages)]

    qv = _embed_query(question)
    sims = M @ qv  # косинус (M и qv нормированы)

    if not rerank:
        idx = sims.argsort()[::-1][:top_k]
        return [
            {"text": passages[i]["text"], "score": float(sims[i]), "source": passages[i]["source"]}
            for i in idx
        ]

    # rerank=True: пул top-N по косинусу -> кросс-энкодер bge-reranker-v2-m3 (движок Гефеста).
    from reranker_model import CrossEncoderReranker  # ленивый импорт: тянет torch/transformers
    rerank_n = int(os.getenv("RERANK_N", "20"))
    pool = sims.argsort()[::-1][:rerank_n]
    cands = [{"text": passages[i]["text"], "source": passages[i]["source"]} for i in pool]
    rk = CrossEncoderReranker()
    ranked = rk.rerank(question, cands, top_k=top_k, text_key="text")
    return [
        {"text": c["text"], "score": float(s), "source": c["source"]}
        for c, s in ranked
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
