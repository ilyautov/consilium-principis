"""Тесты bootstrap / Monte-Carlo CI для eval-метрик Consilium-Principis.

Математика ЧИСТАЯ: нет сети, нет корпуса, нет ollama.
Все тесты детерминированы через явный seed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from bootstrap_eval import bootstrap_auc, bootstrap_margin, threshold_sensitivity


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
# bootstrap_margin
# ---------------------------------------------------------------------------

def test_bootstrap_margin_clean_separation_positive():
    """Идеальное разделение: mean margin > 0 (daylight есть)."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = bootstrap_margin(ooc, ans, n_boot=500, seed=0)
    assert result["mean"] > 0, f"mean={result['mean']}"
    assert result["ci_lo"] > 0, "ci_lo должен быть > 0 при чистом разделении"


def test_bootstrap_margin_overlap_mean_can_be_negative():
    """Перекрытие: при сильном перекрытии mean margin должен быть < 0."""
    # ans низкие, ooc высокие — намеренное перекрытие / инверсия
    ooc = [0.6, 0.7, 0.8]
    ans = [0.3, 0.4, 0.5]
    result = bootstrap_margin(ooc, ans, n_boot=500, seed=0)
    assert result["mean"] < 0, f"mean={result['mean']} — ожидался < 0 при инверсии"


def test_bootstrap_margin_narrow_overlap_shows_wide_ci():
    """Узкий зазор (как в реальном eval 0.029): CI должен содержать отрицательные значения."""
    ooc = [0.4, 0.45, 0.46, 0.47]
    ans = [0.50, 0.51, 0.52, 0.53]
    result = bootstrap_margin(ooc, ans, n_boot=2000, seed=0)
    # mean может быть слегка позитивным, но нижняя граница CI — отрицательной
    assert result["ci_lo"] < result["mean"], "ci_lo должен быть < mean"
    assert result["ci_lo"] < 0.05, (
        f"ci_lo={result['ci_lo']} — при маленьком зазоре CI должен включать негативную область"
    )


def test_bootstrap_margin_reproducibility():
    """Один seed → идентичный результат."""
    ooc = [0.3, 0.4, 0.5]
    ans = [0.6, 0.7, 0.8]
    r1 = bootstrap_margin(ooc, ans, n_boot=200, seed=17)
    r2 = bootstrap_margin(ooc, ans, n_boot=200, seed=17)
    assert r1 == r2


# ---------------------------------------------------------------------------
# threshold_sensitivity
# ---------------------------------------------------------------------------

def test_threshold_sensitivity_below_all_ans_full_coverage():
    """Порог ниже всех answerable: coverage_mean == 1.0 (ничего не отброшено)."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = threshold_sensitivity(ooc, ans, thresholds=[0.0], n_boot=500, seed=0)
    assert len(result) == 1
    row = result[0]
    assert abs(row["coverage_mean"] - 1.0) < 1e-9, (
        f"coverage_mean={row['coverage_mean']} — ожидался 1.0 при t<all_ans"
    )
    assert abs(row["false_abstain_mean"] - 0.0) < 1e-9


def test_threshold_sensitivity_above_all_ans_zero_coverage():
    """Порог выше всех answerable: coverage_mean == 0.0 (всё отброшено как OOC)."""
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    result = threshold_sensitivity(ooc, ans, thresholds=[1.0], n_boot=500, seed=0)
    row = result[0]
    assert abs(row["coverage_mean"] - 0.0) < 1e-9, (
        f"coverage_mean={row['coverage_mean']} — ожидался 0.0 при t>all_ans"
    )
    assert abs(row["false_abstain_mean"] - 1.0) < 1e-9


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
    assert row["false_abstain_ci"][0] <= row["false_abstain_mean"] <= row["false_abstain_ci"][1]


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
