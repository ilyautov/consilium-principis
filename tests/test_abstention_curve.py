"""Кривая abstention ↔ ложный-отказ (заменяет вводящий-в-заблуждение headline-%).

Долг (digital-twins research): один % честных-отказов ЗАВЫШАЕТ безопасность — прячет цену
в ложных отказах на in-corpus. Правильно — кривая по порогу + рабочая точка (Youden-knee).
Математика кривой ЧИСТАЯ (не нужны корпус/модель) → тестируем детерминированно.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from abstention_curve import (
    curve_from_scores, best_operating_point, thresholds_from_scores, curve_auc,
)


def test_curve_point_rates_are_fractions():
    # OOC (должны отказывать) скоры низкие; in-corpus (должны отвечать) скоры высокие.
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    pts = curve_from_scores(ooc, ans, [0.5])
    p = pts[0]
    assert p["threshold"] == 0.5
    assert p["honest_abstain"] == 1.0        # все 3 OOC < 0.5 → честный отказ
    assert p["false_abstain"] == 0.0         # ни один in-corpus < 0.5 → нет ложных
    assert abs(p["youden"] - 1.0) < 1e-9     # идеальное разделение


def test_threshold_too_high_causes_false_abstain():
    ooc = [0.1, 0.2]
    ans = [0.6, 0.7]
    pts = curve_from_scores(ooc, ans, [0.65])
    p = pts[0]
    assert p["honest_abstain"] == 1.0        # оба OOC < 0.65
    assert p["false_abstain"] == 0.5         # один in-corpus (0.6) < 0.65 → ЛОЖНЫЙ отказ
    assert abs(p["youden"] - 0.5) < 1e-9


def test_best_operating_point_maximizes_youden():
    ooc = [0.1, 0.2, 0.3]
    ans = [0.6, 0.7, 0.8]
    pts = curve_from_scores(ooc, ans, [0.3, 0.5, 0.65, 0.9])
    best = best_operating_point(pts)
    assert best["threshold"] == 0.5          # 0.5 даёт youden=1.0; 0.9 даёт ложные отказы
    assert abs(best["youden"] - 1.0) < 1e-9


def test_best_operating_point_tie_breaks_to_lower_false_abstain():
    # два порога с равным youden → берём тот, что меньше калечит in-corpus (ниже false_abstain)
    ooc = [0.1]
    ans = [0.9]
    pts = curve_from_scores(ooc, ans, [0.5, 0.85])  # оба: honest=1, false=0, youden=1
    best = best_operating_point(pts)
    assert best["false_abstain"] == 0.0
    assert best["threshold"] == 0.5          # при равенстве — ниже порог (меньше риск ложн. отказа)


def test_thresholds_span_observed_scores():
    thr = thresholds_from_scores([0.1, 0.9], n=5)
    assert len(thr) == 5
    assert abs(thr[0] - 0.1) < 1e-9
    assert abs(thr[-1] - 0.9) < 1e-9
    assert thr == sorted(thr)


def test_thresholds_handles_degenerate_single_value():
    thr = thresholds_from_scores([0.4, 0.4], n=5)
    assert len(thr) >= 1
    assert all(abs(t - 0.4) < 0.5 for t in thr)   # не падает, диапазон вокруг значения


def test_auc_perfect_separation_is_one():
    # AUC по точкам кривой (honest как «выигрыш», 1-false как «сохранность») — идеал → 1.0
    ooc = [0.1, 0.2, 0.3, 0.4]
    ans = [0.6, 0.7, 0.8, 0.9]
    auc = curve_auc(ooc, ans)
    assert auc > 0.99


def test_auc_no_separation_is_half():
    # одинаковые распределения → порог не различает → AUC ≈ 0.5
    ooc = [0.5, 0.5, 0.5, 0.5]
    ans = [0.5, 0.5, 0.5, 0.5]
    auc = curve_auc(ooc, ans)
    assert abs(auc - 0.5) < 0.2


def test_empty_inputs_do_not_crash():
    pts = curve_from_scores([], [], [0.5])
    assert pts[0]["honest_abstain"] == 0.0
    assert pts[0]["false_abstain"] == 0.0
    assert best_operating_point([]) is None
