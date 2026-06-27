#!/usr/bin/env python3
"""Adversarial-пертурбация ситуационной карты (борроу #2 из MiroFish, на нашей стороне рва).

Не «дать умный ответ», а проверить: ДЕРЖИТСЯ ли твоя линия, когда мир дрогнет. Возмущаем
позицию и мир (силу/обоснованность ходов, новые угрозы) — НЕ уста советников (фабрикацию
по-прежнему не пускаем). Над `situation.evaluate`, поэтому чистое и детерминированное.

Виды возмущений (мир-сторона контура):
  • invalidate — премиса/обоснование хода рушится: grounded→False (контур обнулит силу);
  • weaken     — довод слабее, чем казалось: strength *= factor;
  • inject_counter — всплыла контрмера оппонента: добавить opponent-ход под твои заходы.

`stress_test` гоняет N возмущений, считает robustness (доля миров, где вердикт устоял) и
fragile_under (что именно тебя ломает) — карта хрупкости рекомендации.
"""
import copy
from situation import Move, node, evaluate, verdict


def apply_perturbation(tree, pert):
    """Вернуть НОВОЕ дерево с применённым возмущением (оригинал не трогаем)."""
    t = copy.deepcopy(tree)
    kind = pert["kind"]

    if kind == "inject_counter":
        threat = Move("opponent", pert.get("claim", "контрмера"),
                      grounded=pert.get("grounded", True), strength=pert.get("strength", 0.5))
        for child in t["children"]:                  # под каждый ТВОЙ заход
            if child["move"] is not None and child["move"].by == "you":
                child["children"].append(node(copy.deepcopy(threat)))
        return t

    factor = pert.get("factor", 0.5)
    target = pert.get("claim")

    def walk(n):
        m = n["move"]
        if m is not None and m.claim == target:
            if kind == "invalidate":
                m.grounded = False                   # контур обнулит вклад
            elif kind == "weaken":
                m.strength *= factor
        for c in n["children"]:
            walk(c)

    walk(t)
    return t


def stress_test(tree, perturbations, stance="competitive"):
    """Прогнать возмущения. held = вердикт устоял (для competitive — остался winnable, если
    базовый winnable; иначе — тот же класс вердикта). robustness = held/N."""
    base_value = evaluate(tree, stance)
    base_verdict = verdict(base_value, stance)[0]

    results, fragile, held = [], [], 0
    for p in perturbations:
        v = evaluate(apply_perturbation(tree, p), stance)
        k = verdict(v, stance)[0]
        ok = (k == "winnable") if base_verdict == "winnable" else (k == base_verdict)
        results.append({"perturbation": p, "value": v, "verdict": k, "held": ok})
        if ok:
            held += 1
        else:
            fragile.append(p)

    n = len(perturbations)
    return {
        "baseline_value": base_value, "baseline_verdict": base_verdict,
        "n": n, "held": held, "robustness": held / n if n else 1.0,
        "fragile_under": fragile, "results": results,
    }
