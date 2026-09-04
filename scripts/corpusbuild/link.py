"""S1→P1 кросс-язычный семантический мост (русский Тарасов → английский Макиавелли).
nearest_p1 — чистая (тестируема без сети); build_links эмбеддит и зовёт её."""
import sys
import json
from . import embed, ids, paths


def nearest_p1(s1, p1, top_m: int = 3, min_cos: float = 0.45) -> list:
    """s1=(id, vec); p1=[(id, vec)…]. Возвращает ≤top_m рёбер выше порога, по убыванию косинуса."""
    sid, svec = s1
    scored = [(pid, embed.cosine(svec, pvec)) for pid, pvec in p1]
    scored = [(pid, c) for pid, c in scored if c >= min_cos]
    scored.sort(key=lambda t: -t[1])
    return [{"src": sid, "dst": pid, "type": "толкует", "weight": round(c, 4), "cross_lingual": True}
            for pid, c in scored[:top_m]]


def build_links(advisor_dir: str, top_m: int = 3, min_cos: float = 0.45) -> list:
    """Эмбеддит P1- и S1-чанки, строит links.jsonl. Возвращает все рёбра."""
    corpus = ids.load_corpus(advisor_dir)
    p1c = [c for c in corpus if c["tier"] in ("P1", "P2")]
    s1c = [c for c in corpus if c["tier"] in ("S1", "S2")]
    p1vec = embed.embed_texts([c["text"] for c in p1c])
    s1vec = embed.embed_texts([c["text"] for c in s1c])
    p1 = list(zip([c["id"] for c in p1c], p1vec))
    links = []
    for c, v in zip(s1c, s1vec):
        links.extend(nearest_p1((c["id"], v), p1, top_m, min_cos))
    out = f"{paths.build_dir(advisor_dir)}/links.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for l in links:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    print(f"[link] {advisor_dir}: {len(links)} рёбер S1→P1 (из {len(s1c)} S1-чанков) → {out}", file=sys.stderr)
    return links
