"""Adversarial-пертурбация (борроу #2 из MiroFish, на нашей стороне рва).

Их «inject variables» = стресс-тест под возмущениями. Берём для ситуационной карты: держится
ли твоя линия, если мир дрогнет — премиса ложна / довод не обоснуется / всплыла контрмера.
Возмущаем МИР и твою позицию (силу/обоснованность ходов, новые угрозы), НЕ уста советников.
Чистое ядро над situation.evaluate → детерминированный тест. Метрика — robustness: доля
возмущённых миров, где вердикт устоял; fragile_under — что именно тебя ломает.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from situation import Move, node
from perturbation import apply_perturbation, stress_test


def _winnable_tree():
    # ты 0.8, слабый контр 0.2 → value 0.6, winnable
    return node(None, [
        node(Move("you", "мой довод", grounded=True, strength=0.8), [
            node(Move("opponent", "слабый контр", grounded=True, strength=0.2)),
        ]),
    ])


def test_invalidate_key_move_breaks_position():
    t = _winnable_tree()
    p = apply_perturbation(t, {"kind": "invalidate", "claim": "мой довод"})
    from situation import evaluate, verdict
    v = evaluate(p, "competitive")
    assert v < 0                                   # обоснование исчезло → 0 силы, минус контр
    assert verdict(v, "competitive")[0] == "no_winning_line"
    # оригинал не тронут (deep copy)
    assert evaluate(t, "competitive") > 0


def test_weaken_reduces_value():
    t = _winnable_tree()
    from situation import evaluate
    p = apply_perturbation(t, {"kind": "weaken", "claim": "мой довод", "factor": 0.1})
    assert evaluate(p, "competitive") < evaluate(t, "competitive")


def test_inject_counter_adds_opponent_threat():
    t = _winnable_tree()
    from situation import evaluate
    base = evaluate(t, "competitive")
    p = apply_perturbation(t, {"kind": "inject_counter", "claim": "новая угроза",
                               "strength": 0.95})
    v = evaluate(p, "competitive")
    assert v < base                                # minimax возьмёт сильнейшую угрозу (0.95)
    assert abs(v - (0.8 - 0.95)) < 1e-9


def test_mild_counter_does_not_break_robust_position():
    t = _winnable_tree()
    from situation import evaluate, verdict
    p = apply_perturbation(t, {"kind": "inject_counter", "claim": "слабая угроза",
                               "strength": 0.3})
    assert verdict(evaluate(p, "competitive"), "competitive")[0] == "winnable"  # устоял


def test_irrelevant_perturbation_leaves_position_unchanged():
    t = _winnable_tree()
    from situation import evaluate
    p = apply_perturbation(t, {"kind": "invalidate", "claim": "несуществующий ход"})
    assert evaluate(p, "competitive") == evaluate(t, "competitive")


def test_stress_test_reports_robustness_and_fragility():
    t = _winnable_tree()
    perts = [
        {"kind": "invalidate", "claim": "мой довод"},        # ломает
        {"kind": "invalidate", "claim": "несуществующий"},   # не трогает
        {"kind": "inject_counter", "claim": "killer", "strength": 0.99},  # ломает
    ]
    res = stress_test(t, perts, stance="competitive")
    assert res["baseline_verdict"] == "winnable"
    assert res["n"] == 3
    assert res["held"] == 1                          # устоял только под нерелевантной
    assert abs(res["robustness"] - 1/3) < 1e-9
    assert len(res["fragile_under"]) == 2


def test_robust_position_full_score():
    t = _winnable_tree()
    perts = [{"kind": "inject_counter", "claim": "слабая", "strength": 0.1},
             {"kind": "weaken", "claim": "мой довод", "factor": 0.9}]
    res = stress_test(t, perts, stance="competitive")
    assert res["robustness"] == 1.0                  # обе не сломали
    assert res["fragile_under"] == []
