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


def rrf_fuse(ranked_lists, k: int = 60, top_k=None, weights=None):
    """ranked_lists: список списков Passage (каждый уже отсортирован по убыванию релевантности).
    weights: опц. вес на список (по умолчанию 1.0 у всех). Выше вес у оригинального запроса →
    multi-query ДОПОЛНЯЕТ, а не топит single (лечит структурную дилюцию).
    Возвращает один список Passage со слитым RRF-score, по убыванию. Дедуп по нормализованному тексту."""
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    agg = {}  # key -> [fused_score, Passage]
    for lst, w in zip(ranked_lists, weights):
        for rank, p in enumerate(lst, 1):
            kk = _key(p.text)
            if not kk:
                continue
            if kk not in agg:
                agg[kk] = [0.0, p]
            agg[kk][0] += w / (k + rank)
    # tier берём у представителя (первого встреченного пассажа с этим текстом): один и тот же
    # текст в разных списках — один и тот же чанк корпуса, тир у него общий.
    fused = [Passage(text=p.text, score=score, source=p.source, tier=p.tier)
             for score, p in agg.values()]
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused[:top_k] if top_k else fused
