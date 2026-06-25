"""Reciprocal Rank Fusion — переиспользуемый примитив слияния ранжированных списков.

Один и тот же фьюзер обслуживает:
  • Левер 1: слить semantic ∪ lexical (разная granularity — чанки/предложения, это ок);
  • Левер 2: слить выдачи N перефразировок запроса (multi-query / STORM).

«Нечёткая логика» в чистом виде: пассаж, всплывший у НЕСКОЛЬКИХ источников/перефразировок,
получает более высокий слитый score (мягкий консенсус), без жёсткого «топ-1 или мимо».
score(p) = Σ_i 1/(k + rank_i(p)).  k гасит вклад хвоста (стандарт k=60, Cormack 2009).
"""
import re
from . import Passage


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


def rrf_fuse(ranked_lists, k: int = 60, top_k=None):
    """ranked_lists: список списков Passage (каждый уже отсортирован по убыванию релевантности).
    Возвращает один список Passage со слитым RRF-score, по убыванию. Дедуп по нормализованному тексту."""
    agg = {}  # key -> [fused_score, Passage]
    for lst in ranked_lists:
        for rank, p in enumerate(lst, 1):
            kk = _key(p.text)
            if not kk:
                continue
            if kk not in agg:
                agg[kk] = [0.0, p]
            agg[kk][0] += 1.0 / (k + rank)
    fused = [Passage(text=p.text, score=score, source=p.source) for score, p in agg.values()]
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused[:top_k] if top_k else fused
