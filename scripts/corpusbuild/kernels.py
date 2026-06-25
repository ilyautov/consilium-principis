"""Извлечь мета-идеи (кернелы) и ЗАЗЕМЛИТЬ их к P1-пассажам. L2.3.1: безземельный кернел не существует.
Экстракция переиспользует уже фальсиф-валидную логику exp_kernels (отдельный скрипт). ground_kernel /
drop_groundless — чистые, тестируемы без сети."""
import json
from . import embed, ids, paths


def ground_kernel(kvec, p1, ground_n: int = 5, min_cos: float = 0.45) -> list:
    """Топ-N ближайших P1-id выше порога. p1=[(id, vec)…]."""
    scored = [(pid, embed.cosine(kvec, pvec)) for pid, pvec in p1]
    scored = [(pid, c) for pid, c in scored if c >= min_cos]
    scored.sort(key=lambda t: -t[1])
    return [pid for pid, _ in scored[:ground_n]]


def drop_groundless(items: list) -> list:
    """Выкинуть кернелы без заземления (L2.3.1)."""
    return [k for k in items if k.get("grounded_in")]


def build_kernels(advisor_dir: str, author: str, k: int = 6, ground_n: int = 5, min_cos: float = 0.45) -> list:
    """extract (gemma) → embed → ground → drop groundless → kernels.json."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/ на путь
    from exp_kernels import extract_kernels  # уже валидная экстракция
    corpus = ids.load_corpus(advisor_dir)
    p1c = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c.get("text", "")) > 250]
    names = extract_kernels(author, [{"text": c["text"]} for c in p1c], k=k)
    kvecs = embed.embed_texts(names)
    p1vec = embed.embed_texts([c["text"] for c in p1c])
    p1 = list(zip([c["id"] for c in p1c], p1vec))
    items = [{"name": n, "method": n, "grounded_in": ground_kernel(kv, p1, ground_n, min_cos)}
             for n, kv in zip(names, kvecs)]
    items = drop_groundless(items)
    out = f"{paths.build_dir(advisor_dir)}/kernels.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"[kernels] {advisor_dir}: {len(items)} заземлённых кернелов → {out}")
    return items
