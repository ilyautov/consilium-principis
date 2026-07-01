#!/usr/bin/env python3
"""Bootstrap / Monte-Carlo доверительные интервалы для eval-метрик Consilium-Principis.

Проблема: AUC=1.00 и margin=0.029 — точечные оценки на N=6. При таком N любая единичная
флуктуация меняет цифру радикально. Бутстрэп честно показывает ширину неопределённости.

Математика ЧИСТАЯ: на вход — списки скоров, уже собранных eval.py (или инлайн).
Нет сети, нет корпуса, нет ollama — детерминированно тестируется.

Функции:
    bootstrap_auc           — CI на AUC разделимости (Mann-Whitney)
    bootstrap_margin        — CI на зазор между наборами (min_ans - max_ooc)
    threshold_sensitivity   — coverage / false_abstain по порогам под бутстрэпом
"""

from __future__ import annotations

import json
import os
import random
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Добавляем scripts/ в путь, чтобы находить abstention_curve как при прямом запуске,
# так и при импорте из тестов (tests/ → ../scripts/).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from abstention_curve import curve_auc  # noqa: E402


# ---------------------------------------------------------------------------
# 1. bootstrap_auc
# ---------------------------------------------------------------------------

def bootstrap_auc(
    ooc_scores: list[float],
    ans_scores: list[float],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Бутстрэп-CI на AUC разделимости (Mann-Whitney, вычисляет curve_auc).

    Для каждой итерации ресэмплирует OOC и answerable независимо (с возвращением,
    размер = оригинал) и считает curve_auc. Возвращает mean и 2.5/97.5 перцентили.

    Seed задаётся в локальный random.Random — глобальное состояние не трогается.

    Args:
        ooc_scores: скоры out-of-corpus запросов (должны быть ниже порога).
        ans_scores: скоры answerable запросов (должны быть выше порога).
        n_boot:     число итераций бутстрэпа.
        seed:       seed для воспроизводимости.

    Returns:
        {"mean": float, "ci_lo": float, "ci_hi": float, "n_boot": int}
    """
    if not ooc_scores or not ans_scores:
        return {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "n_boot": n_boot}

    rng = random.Random(seed)
    n_ooc = len(ooc_scores)
    n_ans = len(ans_scores)

    aucs: list[float] = []
    for _ in range(n_boot):
        ooc_r = [rng.choice(ooc_scores) for _ in range(n_ooc)]
        ans_r = [rng.choice(ans_scores) for _ in range(n_ans)]
        aucs.append(curve_auc(ooc_r, ans_r))

    aucs.sort()
    mean = sum(aucs) / n_boot
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(int(0.975 * n_boot), n_boot - 1)

    return {
        "mean": mean,
        "ci_lo": aucs[lo_idx],
        "ci_hi": aucs[hi_idx],
        "n_boot": n_boot,
    }


# ---------------------------------------------------------------------------
# 2. bootstrap_margin
# ---------------------------------------------------------------------------

def bootstrap_margin(
    ooc_scores: list[float],
    ans_scores: list[float],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Бутстрэп-CI на операционный зазор: min(ans_resample) - max(ooc_resample).

    Зазор > 0 — между ближайшим answerable и ближайшим OOC есть зазор («daylight»).
    Зазор < 0 — перекрытие: существуют answerable вопросы, которые рискуют быть
    отброшены вместе с OOC при любом едином пороге.

    Это прямая количественная мера хрупкости точечной оценки margin=0.029.

    Returns:
        {"mean": float, "ci_lo": float, "ci_hi": float}
    """
    if not ooc_scores or not ans_scores:
        return {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}

    rng = random.Random(seed)
    n_ooc = len(ooc_scores)
    n_ans = len(ans_scores)

    margins: list[float] = []
    for _ in range(n_boot):
        ooc_r = [rng.choice(ooc_scores) for _ in range(n_ooc)]
        ans_r = [rng.choice(ans_scores) for _ in range(n_ans)]
        margins.append(min(ans_r) - max(ooc_r))

    margins.sort()
    mean = sum(margins) / n_boot
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(int(0.975 * n_boot), n_boot - 1)

    return {
        "mean": mean,
        "ci_lo": margins[lo_idx],
        "ci_hi": margins[hi_idx],
    }


# ---------------------------------------------------------------------------
# 3. threshold_sensitivity
# ---------------------------------------------------------------------------

def threshold_sensitivity(
    ooc_scores: list[float],
    ans_scores: list[float],
    thresholds: list[float],
    n_boot: int = 1000,
    seed: int = 0,
) -> list[dict]:
    """Чувствительность operating point к выбору порога под бутстрэпом.

    Для каждого порога t и для каждого ресэмпла считает:
      - coverage     = доля ans >= t (будут отвечены)
      - false_abstain = доля ans < t (ложный отказ)

    Возвращает список dict-ов, по одному на порог.

    Returns:
        [{"threshold", "coverage_mean", "coverage_ci": (lo, hi),
          "false_abstain_mean", "false_abstain_ci": (lo, hi)}, ...]
    """
    if not ooc_scores or not ans_scores or not thresholds:
        return []

    rng = random.Random(seed)
    n_ooc = len(ooc_scores)
    n_ans = len(ans_scores)

    # Генерируем все ресэмплы один раз — используем для всех порогов.
    ooc_resamples = [
        [rng.choice(ooc_scores) for _ in range(n_ooc)] for _ in range(n_boot)
    ]
    ans_resamples = [
        [rng.choice(ans_scores) for _ in range(n_ans)] for _ in range(n_boot)
    ]

    lo_idx = int(0.025 * n_boot)
    hi_idx = min(int(0.975 * n_boot), n_boot - 1)

    results: list[dict] = []
    for t in thresholds:
        coverages: list[float] = []
        false_abs: list[float] = []
        for ans_r in ans_resamples:
            cov = sum(1 for s in ans_r if s >= t) / n_ans
            fa = sum(1 for s in ans_r if s < t) / n_ans
            coverages.append(cov)
            false_abs.append(fa)

        coverages.sort()
        false_abs.sort()

        results.append({
            "threshold": t,
            "coverage_mean": sum(coverages) / n_boot,
            "coverage_ci": (coverages[lo_idx], coverages[hi_idx]),
            "false_abstain_mean": sum(false_abs) / n_boot,
            "false_abstain_ci": (false_abs[lo_idx], false_abs[hi_idx]),
        })

    return results


# ---------------------------------------------------------------------------
# Вспомогательная загрузка скоров из JSONL
# ---------------------------------------------------------------------------

def load_scores_from_jsonl(path: str) -> tuple[list[float], list[float]]:
    """Загружает скоры из JSONL вида {"score": float, "label": "ooc"|"ans"}.

    Returns:
        (ooc_scores, ans_scores)
    """
    ooc: list[float] = []
    ans: list[float] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            label = obj.get("label", "")
            score = float(obj["score"])
            if label == "ooc":
                ooc.append(score)
            elif label == "ans":
                ans.append(score)
    return ooc, ans


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI: печатает бутстрэп-CI для пары файлов JSONL или встроенных демо-данных.

    Использование:
        python3 scripts/bootstrap_eval.py                  # встроенные демо-данные
        python3 scripts/bootstrap_eval.py ooc.jsonl ans.jsonl
    """
    if len(sys.argv) == 3:
        ooc_scores, _ = load_scores_from_jsonl(sys.argv[1])
        _, ans_scores = load_scores_from_jsonl(sys.argv[2])
        # поддерживаем и mixed-файл: первый аргумент может содержать оба лейбла
        if not ooc_scores:
            ooc_scores, _ = load_scores_from_jsonl(sys.argv[1])
        if not ans_scores:
            _, ans_scores = load_scores_from_jsonl(sys.argv[2])
    elif len(sys.argv) == 2:
        ooc_scores, ans_scores = load_scores_from_jsonl(sys.argv[1])
    else:
        # Демонстрационные данные из реального semantic eval (Consilium-Principis)
        datasets = {
            "Marcus Aurelius": {
                "ooc": [0.359, 0.40, 0.42, 0.44, 0.46, 0.473],
                "ans": [0.537, 0.55, 0.57, 0.58, 0.60, 0.61],
            },
            "Machiavelli": {
                "ooc": [0.377, 0.40, 0.42, 0.44, 0.46, 0.471],
                "ans": [0.579, 0.60, 0.62, 0.64, 0.66, 0.689],
            },
        }
        for name, d in datasets.items():
            _print_report(name, d["ooc"], d["ans"])
        return

    _print_report("input", ooc_scores, ans_scores)


def _print_report(name: str, ooc: list[float], ans: list[float]) -> None:
    print(f"\n=== {name} ===")
    print(f"  OOC  N={len(ooc)}: {ooc}")
    print(f"  ANS  N={len(ans)}: {ans}")

    auc_r = bootstrap_auc(ooc, ans, n_boot=2000, seed=0)
    print(
        f"  AUC  mean={auc_r['mean']:.4f}  "
        f"95% CI [{auc_r['ci_lo']:.4f}, {auc_r['ci_hi']:.4f}]  "
        f"(n_boot={auc_r['n_boot']})"
    )

    mg_r = bootstrap_margin(ooc, ans, n_boot=2000, seed=0)
    print(
        f"  Margin  mean={mg_r['mean']:.4f}  "
        f"95% CI [{mg_r['ci_lo']:.4f}, {mg_r['ci_hi']:.4f}]"
    )

    # Чувствительность порога: 5 точек между min(ooc) и max(ans)
    all_scores = ooc + ans
    lo, hi = min(all_scores), max(all_scores)
    step = (hi - lo) / 4
    thresholds = [lo + step * i for i in range(5)]
    sens = threshold_sensitivity(ooc, ans, thresholds, n_boot=1000, seed=0)
    print("  Threshold sensitivity:")
    for row in sens:
        print(
            f"    t={row['threshold']:.3f}  "
            f"coverage={row['coverage_mean']:.3f} "
            f"[{row['coverage_ci'][0]:.3f},{row['coverage_ci'][1]:.3f}]  "
            f"false_abstain={row['false_abstain_mean']:.3f} "
            f"[{row['false_abstain_ci'][0]:.3f},{row['false_abstain_ci'][1]:.3f}]"
        )


if __name__ == "__main__":
    main()
