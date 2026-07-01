#!/usr/bin/env python3
"""Bootstrap / Monte-Carlo доверительные интервалы для eval-метрик Consilium-Principis.

Проблема: AUC=1.00 и margin=0.029 — точечные оценки на N=6. При таком N любая единичная
флуктуация меняет цифру радикально. Бутстрэп честно показывает ширину неопределённости.

Математика ЧИСТАЯ: на вход — списки скоров, уже собранных eval.py (или инлайн).
Нет сети, нет корпуса, нет ollama — детерминированно тестируется.

Функции:
    bootstrap_auc               — CI на AUC разделимости (Mann-Whitney)
    bootstrap_overlap           — CI на долю инверсий (вероятность провала рва)
    bootstrap_quantile_daylight — CI на робастный зазор (может уходить в минус)
    point_margin                — сырой min_ans-max_ooc БЕЗ CI (нельзя бутстрэпить)
    threshold_sensitivity       — coverage / false_accept по порогам под бутстрэпом

ВАЖНО: min/max-margin НЕ бутстрэпится. Непараметрический бутстрэп несостоятелен на
экстремальных порядковых статистиках (Bickel–Freedman): ci_lo прибивается к точечной
оценке → «интервал» ложно уверяет «зазор НЕ МЕНЬШЕ X». Честную неопределённость дают
bootstrap_overlap (гладкая доля инверсий) и bootstrap_quantile_daylight (гладкие квантили).
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

def point_margin(ooc_scores: list[float], ans_scores: list[float]) -> dict:
    """Сырой операционный зазор: min(ans) - max(ooc). БЕЗ доверительного интервала.

    ВНИМАНИЕ: это точечный дескриптор на ЭКСТРЕМАЛЬНЫХ порядковых статистиках
    (минимум/максимум). Непараметрический бутстрэп на нём НЕСОСТОЯТЕЛЕН
    (Bickel–Freedman 1981): ресэмплинг с возвращением не может выбрать значение
    ниже min(ans) или выше max(ooc), поэтому каждый ресэмплированный зазор >=
    точечной оценки → ci_lo прибивается снизу К самой точечной оценке. Такой
    «интервал» рекламирует хрупкость, а на деле утверждает «зазор НЕ МЕНЬШЕ X» —
    прямо противоположное, давая ложную уверенность в рве.

    Поэтому его НЕЛЬЗЯ бутстрэпить. Для честной неопределённости используй
    bootstrap_overlap (доля инверсий) и bootstrap_quantile_daylight (робастный зазор).

    Returns:
        {"point_margin": float}  # положительный = зазор, отрицательный = перекрытие
    """
    if not ooc_scores or not ans_scores:
        return {"point_margin": 0.0}
    return {"point_margin": min(ans_scores) - max(ooc_scores)}


def bootstrap_overlap(
    ooc_scores: list[float],
    ans_scores: list[float],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Бутстрэп-CI на долю ИНВЕРСИЙ (overlap) — вероятность провала рва.

    Для каждого ресэмпла: доля пар (o из ooc_r, a из ans_r) с o >= a — то есть
    доля случаев, когда OOC-вопрос набирает НЕ МЕНЬШЕ реального (утечка сквозь порог).
    Это гладкий функционал (среднее по парам), поэтому бутстрэп СОСТОЯТЕЛЕН.

      - чистое разделение → ~0 с узким CI;
      - реальное перекрытие → >0 с реально расширяющимся CI (честная хрупкость).

    Returns:
        {"mean": float, "ci_lo": float, "ci_hi": float, "n_boot": int}
    """
    if not ooc_scores or not ans_scores:
        return {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "n_boot": n_boot}

    rng = random.Random(seed)
    n_ooc = len(ooc_scores)
    n_ans = len(ans_scores)

    fracs: list[float] = []
    for _ in range(n_boot):
        ooc_r = [rng.choice(ooc_scores) for _ in range(n_ooc)]
        ans_r = sorted(rng.choice(ans_scores) for _ in range(n_ans))
        # Для каждого o считаем, сколько a <= o (инверсии), через бинарный поиск.
        inversions = 0
        for o in ooc_r:
            # число a c a <= o = bisect_right(ans_r, o)
            inversions += _bisect_right(ans_r, o)
        fracs.append(inversions / (n_ooc * n_ans))

    fracs.sort()
    mean = sum(fracs) / n_boot
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(int(0.975 * n_boot), n_boot - 1)

    return {
        "mean": mean,
        "ci_lo": fracs[lo_idx],
        "ci_hi": fracs[hi_idx],
        "n_boot": n_boot,
    }


def bootstrap_quantile_daylight(
    ooc_scores: list[float],
    ans_scores: list[float],
    n_boot: int = 2000,
    seed: int = 0,
    q: float = 0.1,
) -> dict:
    """Бутстрэп-CI на РОБАСТНЫЙ зазор: quantile(ans, q) - quantile(ooc, 1-q).

    По умолчанию 10-й перцентиль answerable минус 90-й перцентиль OOC. В отличие
    от min/max-margin, квантили — ГЛАДКИЕ функционалы, поэтому бутстрэп состоятелен,
    и зазор МОЖЕТ уходить в минус, когда робастные полосы перекрываются (честная
    оценка downside рва).

    Returns:
        {"mean": float, "ci_lo": float, "ci_hi": float}
    """
    if not ooc_scores or not ans_scores:
        return {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}

    rng = random.Random(seed)
    n_ooc = len(ooc_scores)
    n_ans = len(ans_scores)

    daylights: list[float] = []
    for _ in range(n_boot):
        ooc_r = [rng.choice(ooc_scores) for _ in range(n_ooc)]
        ans_r = [rng.choice(ans_scores) for _ in range(n_ans)]
        daylights.append(_quantile(ans_r, q) - _quantile(ooc_r, 1.0 - q))

    daylights.sort()
    mean = sum(daylights) / n_boot
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(int(0.975 * n_boot), n_boot - 1)

    return {
        "mean": mean,
        "ci_lo": daylights[lo_idx],
        "ci_hi": daylights[hi_idx],
    }


def _quantile(values: list[float], p: float) -> float:
    """p-й квантиль (p∈[0,1]) с линейной интерполяцией. Не мутирует вход."""
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    p = max(0.0, min(1.0, p))
    idx = p * (len(xs) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(xs) - 1)
    frac = idx - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def _bisect_right(sorted_xs: list[float], v: float) -> int:
    """Число элементов sorted_xs <= v (позиция вставки справа)."""
    lo, hi = 0, len(sorted_xs)
    while lo < hi:
        mid = (lo + hi) // 2
        if v < sorted_xs[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


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
    """Чувствительность operating point к выбору порога под бутстрэпом — ОБЕ стороны.

    Для каждого порога t и для каждого ресэмпла считает:
      - coverage     = доля ans >= t (реальные вопросы, которые ответим)
      - false_accept = доля ooc >= t (OOC-утечка сквозь порог — прямой провал рва)

    false_accept — ров-релевантная половина: показывает, сколько OOC-вопросов
    просачивается при данном пороге. (Прежний false_abstain был просто 1-coverage,
    избыточен, поэтому убран.)

    Returns:
        [{"threshold", "coverage_mean", "coverage_ci": (lo, hi),
          "false_accept_mean", "false_accept_ci": (lo, hi)}, ...]
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
        false_acc: list[float] = []
        for ans_r in ans_resamples:
            coverages.append(sum(1 for s in ans_r if s >= t) / n_ans)
        for ooc_r in ooc_resamples:
            false_acc.append(sum(1 for s in ooc_r if s >= t) / n_ooc)

        coverages.sort()
        false_acc.sort()

        results.append({
            "threshold": t,
            "coverage_mean": sum(coverages) / n_boot,
            "coverage_ci": (coverages[lo_idx], coverages[hi_idx]),
            "false_accept_mean": sum(false_acc) / n_boot,
            "false_accept_ci": (false_acc[lo_idx], false_acc[hi_idx]),
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
        # два файла: OOC-скоры из первого, answerable из второго
        ooc_scores, _ = load_scores_from_jsonl(sys.argv[1])
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

    # Overlap-фракция (доля инверсий) — bootstrap-состоятельная мера провала рва.
    ov_r = bootstrap_overlap(ooc, ans, n_boot=2000, seed=0)
    print(
        f"  Overlap(инверсии)  mean={ov_r['mean']:.4f}  "
        f"95% CI [{ov_r['ci_lo']:.4f}, {ov_r['ci_hi']:.4f}]"
    )

    # Квантильный зазор — робастный margin, МОЖЕТ уходить в минус.
    qd_r = bootstrap_quantile_daylight(ooc, ans, n_boot=2000, seed=0, q=0.1)
    print(
        f"  Quantile daylight (q=0.1)  mean={qd_r['mean']:.4f}  "
        f"95% CI [{qd_r['ci_lo']:.4f}, {qd_r['ci_hi']:.4f}]"
    )

    # Сырой зазор — точечный дескриптор БЕЗ CI (нельзя бутстрэпить).
    pm = point_margin(ooc, ans)
    print(f"  point_margin (без CI, extreme-order-stat)  = {pm['point_margin']:.4f}")

    # Чувствительность порога: 5 точек между min(ooc) и max(ans)
    all_scores = ooc + ans
    lo, hi = min(all_scores), max(all_scores)
    step = (hi - lo) / 4
    thresholds = [lo + step * i for i in range(5)]
    sens = threshold_sensitivity(ooc, ans, thresholds, n_boot=1000, seed=0)
    print("  Threshold sensitivity (coverage answerable / false_accept OOC-утечка):")
    for row in sens:
        print(
            f"    t={row['threshold']:.3f}  "
            f"coverage={row['coverage_mean']:.3f} "
            f"[{row['coverage_ci'][0]:.3f},{row['coverage_ci'][1]:.3f}]  "
            f"false_accept={row['false_accept_mean']:.3f} "
            f"[{row['false_accept_ci'][0]:.3f},{row['false_accept_ci'][1]:.3f}]"
        )


if __name__ == "__main__":
    main()
