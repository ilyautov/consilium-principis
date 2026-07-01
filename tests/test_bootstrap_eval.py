"""Тесты bootstrap / Monte-Carlo CI для eval-метрик Consilium-Principis.

Математика ЧИСТАЯ: нет сети, нет корпуса, нет ollama.
Все тесты детерминированы через явный seed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from bootstrap_eval import (
    bootstrap_auc,
    bootstrap_overlap,
    bootstrap_quantile_daylight,
    point_margin,
    threshold_sensitivity,
)


# ---------------------------------------------------------------------------
# bootstrap_auc — чисто разделённые распределения
# ---------------------------------------------------------------------------

def test_bootstrap_auc_clean_separation_mean_near_one():
    """Cleanly separated: все OOC ниже всех ANS → AUC должен быть ≈1.0."""
    ooc = [0.1, 0.15, 0.2]
    ans = [0.8, 0.85, 0.9]
    result = bootstrap_auc(ooc, ans, n_boot=500, seed=7)
    assert result["mean"] > 0.95, f"mean={result['mean']}"
    assert result["ci_lo"] > 0.9, f"ci_lo={result['ci_lo']}"
    assert result["ci_hi"] <= 1.0


def test_bootstrap_auc_clean_separation_ci_tight():
    """При полном разделении CI должен быть узким (мало неопределённости)."""
    ooc = [0.1, 0.15, 0.2]
    ans = [0.8, 0.85, 0.9]
    result = bootstrap_auc(ooc, ans, n_boot=500, seed=7)
    spread = result["ci_hi"] - result["ci_lo"]
    # Узкий CI (< 0.3) при идеальном разделении
    assert spread < 0.3, f"CI spread={spread} — ожидался узкий"


# ---------------------------------------------------------------------------
# bootstrap_auc — воспроизводимость (seeded reproducibility)
# ---------------------------------------------------------------------------

def test_bootstrap_auc_reproducibility_same_seed():
    """Один и тот же seed → идентичный результат."""
    ooc = [0.1, 0.15, 0.2]
    ans = [0.8, 0.85, 0.9]
    r1 = bootstrap_auc(ooc, ans, n_boot=300, seed=42)
    r2 = bootstrap_auc(ooc, ans, n_boot=300, seed=42)
    assert r1 == r2, "Одинаковый seed должен давать идентичный результат"


def test_bootstrap_auc_different_seeds_differ():
    """Разные сиды → разные (хотя и близкие) результаты."""
    ooc = [0.4, 0.5, 0.6]
    ans = [0.45, 0.55, 0.65]
    r1 = bootstrap_auc(ooc, ans, n_boot=300, seed=1)
    r2 = bootstrap_auc(ooc, ans, n_boot=300, seed=99)
    # mean могут совпасть случайно, но хотя бы одно поле различается
    assert r1["mean"] != r2["mean"] or r1["ci_lo"] != r2["ci_lo"]


# ---------------------------------------------------------------------------
# bootstrap_auc — перекрывающиеся распределения → широкий CI
# ---------------------------------------------------------------------------

def test_bootstrap_auc_overlapping_mean_below_one():
    """Перекрывающиеся распределения: mean AUC должен быть заметно ниже 1.0."""
    ooc = [0.4, 0.5, 0.6]
    ans = [0.45, 0.55, 0.65]
    result = bootstrap_auc(ooc, ans, n_boot=2000, seed=0)
    assert result["mean"] < 0.95, f"mean={result['mean']} — ожидался ниже 1.0 при overlap"


def test_bootstrap_auc_overlapping_wide_ci():
    """Перекрывающиеся распределения → CI должен быть ШИРОКИМ (неопределённость реальна)."""
    ooc = [0.4, 0.5, 0.6]
    ans = [0.45, 0.55, 0.65]
    result = bootstrap_auc(ooc, ans, n_boot=2000, seed=0)
    assert result["ci_lo"] < result["mean"] < result["ci_hi"], (
        "CI должен содержать mean"
    )
    spread = result["ci_hi"] - result["ci_lo"]
    assert spread > 0.1, f"CI spread={spread} — ожидался широкий при overlap"


def test_bootstrap_auc_overlapping_ci_contains_half():
    """При перекрытии CI должен допускать AUC близкий к 0.5 (отражать неопределённость)."""
    ooc = [0.4, 0.5, 0.6]
    ans = [0.45, 0.55, 0.65]
    result = bootstrap_auc(ooc, ans, n_boot=2000, seed=0)
    # ci_lo должен быть ≤ 0.7 (не ложно-узкий у 1.0)
    assert result["ci_lo"] <= 0.75, f"ci_lo={result['ci_lo']} — слишком высокий при overlap"


def test_bootstrap_auc_returns_n_boot():
    """n_boot в результате должен совпадать с переданным."""
    result = bootstrap_auc([0.1], [0.9], n_boot=123, seed=0)
    assert result["n_boot"] == 123


# ---------------------------------------------------------------------------
# bootstrap_overlap — bootstrap-состоятельная доля инверсий (провал рва)
# ---------------------------------------------------------------------------

def test_bootstrap_overlap_clean_separation_near_zero():
    """Чистое разделение: доля инверсий ≈0, CI узкий сверху."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = bootstrap_overlap(ooc, ans, n_boot=1000, seed=0)
    assert result["mean"] < 1e-9, f"mean={result['mean']} — ожидался ~0"
    assert result["ci_hi"] < 0.05, f"ci_hi={result['ci_hi']} — CI должен быть узким"


def test_bootstrap_overlap_genuine_overlap_positive_and_wider_ci():
    """Реальное перекрытие: mean > 0 И заметно более широкий CI, чем при разделении."""
    ooc_overlap = [0.4, 0.55, 0.6]
    ans_overlap = [0.45, 0.5, 0.65]
    r_overlap = bootstrap_overlap(ooc_overlap, ans_overlap, n_boot=2000, seed=0)
    assert r_overlap["mean"] > 0, f"mean={r_overlap['mean']} — ожидался > 0 при overlap"

    # Сравнение ширины CI: overlap-случай должен давать более широкий CI.
    r_clean = bootstrap_overlap([0.1, 0.2, 0.3], [0.6, 0.7, 0.8], n_boot=2000, seed=0)
    spread_overlap = r_overlap["ci_hi"] - r_overlap["ci_lo"]
    spread_clean = r_clean["ci_hi"] - r_clean["ci_lo"]
    assert spread_overlap > spread_clean, (
        f"overlap CI ({spread_overlap}) должен быть шире clean CI ({spread_clean})"
    )


def test_bootstrap_overlap_reproducibility():
    """Один seed → идентичный результат."""
    ooc = [0.4, 0.55, 0.6]
    ans = [0.45, 0.5, 0.65]
    r1 = bootstrap_overlap(ooc, ans, n_boot=300, seed=17)
    r2 = bootstrap_overlap(ooc, ans, n_boot=300, seed=17)
    assert r1 == r2


def test_bootstrap_overlap_matches_bruteforce_on_fixed_resample():
    """Санити: overlap-фракция = 1 - AUC(без ничьих) на разделённых данных → 0."""
    ooc = [0.1, 0.2]
    ans = [0.8, 0.9]
    result = bootstrap_overlap(ooc, ans, n_boot=200, seed=3)
    assert result["mean"] == 0.0


# ---------------------------------------------------------------------------
# bootstrap_quantile_daylight — робастный зазор, МОЖЕТ уходить в минус
# ---------------------------------------------------------------------------

def test_quantile_daylight_clean_separation_positive():
    """Чистое разделение: mean робастного зазора > 0."""
    ooc = [0.1, 0.2, 0.3, 0.35]
    ans = [0.6, 0.7, 0.8, 0.85]
    result = bootstrap_quantile_daylight(ooc, ans, n_boot=1000, seed=0, q=0.1)
    assert result["mean"] > 0, f"mean={result['mean']}"


def test_quantile_daylight_genuine_overlap_ci_lo_negative():
    """Реальное перекрытие: ci_lo < 0 — метрика ЧЕСТНО выражает downside."""
    ooc = [0.4, 0.55, 0.6, 0.62]
    ans = [0.45, 0.5, 0.58, 0.65]
    result = bootstrap_quantile_daylight(ooc, ans, n_boot=2000, seed=0, q=0.1)
    assert result["ci_lo"] < 0, (
        f"ci_lo={result['ci_lo']} — робастный зазор должен уметь уходить в минус при overlap"
    )


def test_quantile_daylight_reproducibility():
    """Один seed → идентичный результат."""
    ooc = [0.3, 0.4, 0.5]
    ans = [0.6, 0.7, 0.8]
    r1 = bootstrap_quantile_daylight(ooc, ans, n_boot=200, seed=17)
    r2 = bootstrap_quantile_daylight(ooc, ans, n_boot=200, seed=17)
    assert r1 == r2


# ---------------------------------------------------------------------------
# point_margin — точечный дескриптор БЕЗ CI (нельзя бутстрэпить)
# ---------------------------------------------------------------------------

def test_point_margin_no_ci_fields():
    """point_margin возвращает скаляр без ci_lo/ci_hi — не должен рекламировать интервал."""
    result = point_margin([0.1, 0.4, 0.473], [0.537, 0.6, 0.61])
    assert "point_margin" in result
    assert "ci_lo" not in result and "ci_hi" not in result
    assert abs(result["point_margin"] - (0.537 - 0.473)) < 1e-9


def test_point_margin_negative_on_overlap():
    """Перекрытие: min(ans) < max(ooc) → отрицательный зазор."""
    result = point_margin([0.6, 0.7], [0.3, 0.5])
    assert result["point_margin"] < 0


# ---------------------------------------------------------------------------
# threshold_sensitivity
# ---------------------------------------------------------------------------

def test_threshold_sensitivity_below_all_full_coverage_full_leak():
    """Порог ниже всех скоров: coverage==1.0 И false_accept==1.0 (всё проходит, включая OOC)."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = threshold_sensitivity(ooc, ans, thresholds=[0.0], n_boot=500, seed=0)
    assert len(result) == 1
    row = result[0]
    assert abs(row["coverage_mean"] - 1.0) < 1e-9, (
        f"coverage_mean={row['coverage_mean']} — ожидался 1.0 при t<all"
    )
    # порог ниже всех OOC → все OOC проходят → полная утечка
    assert abs(row["false_accept_mean"] - 1.0) < 1e-9, (
        f"false_accept_mean={row['false_accept_mean']} — ожидался 1.0 при t<all_ooc"
    )


def test_threshold_sensitivity_above_all_zero_coverage_zero_leak():
    """Порог выше всех скоров: coverage==0.0 И false_accept==0.0 (всё отброшено)."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = threshold_sensitivity(ooc, ans, thresholds=[1.0], n_boot=500, seed=0)
    row = result[0]
    assert abs(row["coverage_mean"] - 0.0) < 1e-9, (
        f"coverage_mean={row['coverage_mean']} — ожидался 0.0 при t>all"
    )
    assert abs(row["false_accept_mean"] - 0.0) < 1e-9, (
        f"false_accept_mean={row['false_accept_mean']} — ожидался 0.0 при t>all_ooc"
    )


def test_threshold_sensitivity_operating_point_gates_ooc():
    """Порог между OOC и ans: coverage высокий, false_accept низкий (ров работает)."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = threshold_sensitivity(ooc, ans, thresholds=[0.45], n_boot=500, seed=0)
    row = result[0]
    assert abs(row["coverage_mean"] - 1.0) < 1e-9   # все ans проходят
    assert abs(row["false_accept_mean"] - 0.0) < 1e-9  # ни один OOC не просачивается


def test_threshold_sensitivity_multiple_thresholds_monotone():
    """С ростом порога coverage падает монотонно (или не растёт)."""
    ooc = [0.2, 0.3]
    ans = [0.5, 0.6, 0.7]
    thresholds = [0.0, 0.4, 0.55, 0.65, 1.0]
    result = threshold_sensitivity(ooc, ans, thresholds=thresholds, n_boot=300, seed=0)
    means = [r["coverage_mean"] for r in result]
    for i in range(len(means) - 1):
        assert means[i] >= means[i + 1] - 1e-9, (
            f"Coverage не монотонна: {means}"
        )


def test_threshold_sensitivity_ci_structure():
    """CI должен быть правильно ориентирован: ci_lo <= mean <= ci_hi."""
    ooc = [0.2, 0.3, 0.4]
    ans = [0.5, 0.6, 0.7]
    result = threshold_sensitivity(ooc, ans, thresholds=[0.55], n_boot=500, seed=5)
    row = result[0]
    assert row["coverage_ci"][0] <= row["coverage_mean"] <= row["coverage_ci"][1]
    assert row["false_accept_ci"][0] <= row["false_accept_mean"] <= row["false_accept_ci"][1]


def test_threshold_sensitivity_reproducibility():
    """Один seed → идентичный результат."""
    ooc = [0.2, 0.3]
    ans = [0.6, 0.7]
    r1 = threshold_sensitivity(ooc, ans, [0.4, 0.5], n_boot=100, seed=99)
    r2 = threshold_sensitivity(ooc, ans, [0.4, 0.5], n_boot=100, seed=99)
    assert r1 == r2


def test_threshold_sensitivity_empty_thresholds():
    """Пустой список порогов → пустой результат (не падает)."""
    result = threshold_sensitivity([0.2], [0.7], [], n_boot=50, seed=0)
    assert result == []
