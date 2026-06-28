#!/usr/bin/env python3
"""Калибровка советника по ИСХОДУ — кто реально был прав ДЛЯ ТЕБЯ → вес голоса (петля U1).

track_record_eval (eval.py) считает resolved/pending, но не делает совет умнее: вес всех
голосов равен вечно. Здесь советник, чьи советы вели к ОДОБРЕННЫМ хорошим исходам, получает
больший вес. Метрика — hit = (outcome=good И endorsed): не «послушался», а «легло и одобрено»
(как калибровка подачи). Laplace-сглаживание (Beta(1,1)): без данных вес нейтрален 0.5, не 0
(не хороним нового советника). NB: это hit-rate по исходам, не полный Brier (нет per-совет
вероятности) — апгрейд до Brier, когда советник начнёт давать уверенность.

Записи берутся из relationship.md советников (тонкий адаптер; ядро — на структуре). resolved =
outcome ∈ {good, bad}; pending не учитывается.
"""
from collections import defaultdict


def advisor_scores(records):
    """[{advisor, outcome, endorsed}] → {advisor: {n, resolved, hits, score}}.
    score = (hits+1)/(resolved+2) — доля одобренных хороших исходов с приором 0.5."""
    agg = defaultdict(lambda: {"n": 0, "resolved": 0, "hits": 0})
    for r in records:
        a = agg[r["advisor"]]
        a["n"] += 1
        if r.get("outcome") in ("good", "bad"):
            a["resolved"] += 1
            if r["outcome"] == "good" and r.get("endorsed"):
                a["hits"] += 1
    out = {}
    for name, a in agg.items():
        a["score"] = (a["hits"] + 1) / (a["resolved"] + 2)      # Laplace → нейтраль 0.5
        out[name] = a
    return out


def vote_weights(records):
    """Нормированные веса голосов по score (сумма = 1). Пусто → {}."""
    scores = advisor_scores(records)
    total = sum(a["score"] for a in scores.values())
    if not scores or total == 0:
        return {}
    return {name: a["score"] / total for name, a in scores.items()}
