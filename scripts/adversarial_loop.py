#!/usr/bin/env python3
"""Рекурсивный adversarial-hardening луп для Consilium-Principis.

harden() итеративно генерирует смежно-доменные OOC-вопросы, скорирует их ретривом,
и КОРМИТ ближайшие-к-порогу кейсы (NEAR/BREACH) обратно в генератор как seed_failures,
заставляя следующий раунд делать СЛОЖНЕЕ. Луп — до прорыва рва, до «иссыхания» NEAR/BREACH
или до max_rounds.

Назначение: стресс-тест зазора рва под adversarial pressure. Если daylight держится даже
когда генератор знает, какие вопросы были близки — ров нетривиально устойчив.

СЕАМЫ (инжектируемые зависимости, мокируются в тестах):
    gen_fn(advisor_dir, author, n, seed_failures=None) → [{"q": str, ...}]
    score_fn(question, advisor_dir) → float  # max retrieval score за вопрос

Пример реального запуска:
    from scripts.synth_eval import gen_adversarial_ooc
    from scripts.eval import retrieve

    def score_fn(q, adv_dir):
        hits = retrieve(q, adv_dir, top_k=3)
        return max((h["score"] for h in hits), default=0.0)

    result = harden(
        advisor_dir="advisors/marcus-aurelius",
        author="Marcus Aurelius",
        gen_fn=gen_adversarial_ooc,
        score_fn=score_fn,
    )
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def harden(
    advisor_dir: str,
    author: str,
    gen_fn,
    score_fn,
    threshold: float = 0.50,
    max_rounds: int = 5,
    n_per_round: int = 10,
    near_eps: float = 0.05,
    dry_rounds: int = 2,
    seed: int = 0,  # зарезервирован (RNG не используется в луп-коде, он в gen_fn/score_fn)
) -> dict:
    """Рекурсивный adversarial-hardening луп.

    Параметры:
        advisor_dir   — директория советника (advisors/marcus-aurelius / …).
        author        — имя автора для gen_fn.
        gen_fn        — генератор вопросов (ИНЪЕКЦИЯ; мокируется в тестах).
        score_fn      — scorer вопроса (ИНЪЕКЦИЯ; возвращает max retrieval score).
        threshold     — порог abstain (semantic: 0.50); >= threshold → BREACH.
        max_rounds    — жёсткий лимит раундов.
        n_per_round   — сколько вопросов генерировать за раунд.
        near_eps      — полоса «рядом с порогом»: [threshold-near_eps, threshold) → NEAR.
        dry_rounds    — сколько подряд «сухих» раундов (без новых NEAR/BREACH) перед остановом.
        seed          — параметр воспроизводимости (передаётся в gen_fn/score_fn при необходимости).

    Возвращает:
        {
          "rounds":        [{"round", "n", "max_score", "n_breach", "n_near",
                             "scores": [...], "breaches": [{"q", "score"}]}],
          "all_ooc_scores": [float, ...],   # все max-скоры всех вопросов
          "hardest":       [{"q", "score"}, ...],  # top-5 по score
          "breached":      bool,
          "max_ooc_score": float,
          "stopped_reason": "breach" | "dry" | "max_rounds",
        }
    """
    seeds: list[dict] = []          # NEAR + BREACH из предыдущих раундов → рекурсия
    rounds: list[dict] = []
    all_pairs: list[dict] = []      # {"q", "score"} — все вопросы всех раундов
    all_ooc_scores: list[float] = []
    consecutive_dry = 0
    stopped_reason = "max_rounds"

    for round_no in range(1, max_rounds + 1):
        # ── Генерация ──────────────────────────────────────────────────────────
        questions = gen_fn(
            advisor_dir,
            author,
            n_per_round,
            seed_failures=seeds if seeds else None,
        )

        # ── Скоринг и классификация ────────────────────────────────────────────
        round_scores: list[float] = []
        round_breaches: list[dict] = []
        new_seeds: list[dict] = []
        n_breach = n_near = 0

        for item in questions:
            q = item.get("q", "") if isinstance(item, dict) else str(item)
            s = score_fn(q, advisor_dir)
            round_scores.append(s)
            all_ooc_scores.append(s)
            all_pairs.append({"q": q, "score": s})

            if s >= threshold:
                n_breach += 1
                round_breaches.append({"q": q, "score": s})
                new_seeds.append({"q": q, "why": item.get("why", "") if isinstance(item, dict) else ""})
            elif s >= threshold - near_eps:
                n_near += 1
                new_seeds.append({"q": q, "why": item.get("why", "") if isinstance(item, dict) else ""})

        max_score = max(round_scores) if round_scores else 0.0

        rounds.append({
            "round": round_no,
            "n": len(questions),
            "max_score": max_score,
            "n_breach": n_breach,
            "n_near": n_near,
            "scores": round_scores,
            "breaches": round_breaches,
        })

        # ── Обновление seeds для следующего раунда ─────────────────────────────
        seeds = seeds + new_seeds   # аккумулируем: новые поверх предыдущих

        # ── Условия остановки ──────────────────────────────────────────────────
        if n_breach > 0:
            stopped_reason = "breach"
            break

        if (n_breach + n_near) == 0:
            consecutive_dry += 1
        else:
            consecutive_dry = 0

        if consecutive_dry >= dry_rounds:
            stopped_reason = "dry"
            break

    # ── Финальная сборка ───────────────────────────────────────────────────────
    breached = any(r["n_breach"] > 0 for r in rounds)
    max_ooc_score = max(all_ooc_scores) if all_ooc_scores else 0.0

    # top-5 по score (убывание)
    sorted_pairs = sorted(all_pairs, key=lambda d: d["score"], reverse=True)
    hardest = sorted_pairs[:5]

    return {
        "rounds": rounds,
        "all_ooc_scores": all_ooc_scores,
        "hardest": hardest,
        "breached": breached,
        "max_ooc_score": max_ooc_score,
        "stopped_reason": stopped_reason,
    }
