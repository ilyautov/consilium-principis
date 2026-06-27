"""Движок состязательной/кооперативной ситуации — спина (один атом для трёх фич).

Синтез сессии: решение, спор и действие-в-мире — ОДНА ситуация (ты + оппонент), где
оппонент ∈ {ты, человек, мир}, а верхний параметр — стойка (competitive | cooperative).
Шахматный branch-explorer = один движок; оппонент и eval — параметры.

Тут — ЧИСТОЕ ядро (поиск по уже построенному дереву + оценка + вердикт). Генерация ходов
советниками (LLM) подключается поверх. Инварианты, которые ядро гарантирует:
  • контур: нельзя выиграть ФАБРИКАЦИЕЙ — необоснованный ход (grounded=False) даёт 0 силы;
  • честность: если выигрышной линии нет — движок ГОВОРИТ это (как шахматный движок про −5);
  • minimax: оппонент играет свою СИЛЬНЕЙШУЮ контрмеру, не слабейшую;
  • стойка: competitive = твой перевес над оппонентом; cooperative = совместная ценность.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from situation import (
    Move, node, evaluate, principal_variation, verdict, analyze,
)


def test_grounded_attack_with_weak_reply_is_winnable():
    tree = node(None, [
        node(Move("you", "сильный довод", grounded=True, strength=0.8), [
            node(Move("opponent", "слабая отговорка", grounded=True, strength=0.2)),
        ]),
    ])
    v = evaluate(tree, stance="competitive")
    assert v > 0
    assert verdict(v, "competitive")[0] == "winnable"


def test_fabrication_does_not_win():
    # необоснованный (grounded=False) ход огромной «силы» → контур обнуляет вклад
    tree = node(None, [
        node(Move("you", "блеф-цитата", grounded=False, strength=9.9)),
    ])
    v = evaluate(tree, stance="competitive")
    assert v == 0.0                       # фабрикацией не выигрывают
    assert verdict(v, "competitive")[0] == "no_winning_line"


def test_honest_loss_reported_when_opponent_has_strong_counter():
    tree = node(None, [
        node(Move("you", "твой довод", grounded=True, strength=0.4), [
            node(Move("opponent", "сильное опровержение", grounded=True, strength=0.9)),
        ]),
    ])
    v = evaluate(tree, stance="competitive")
    assert v < 0                          # 0.4 − 0.9
    kind, _ = verdict(v, "competitive")
    assert kind == "no_winning_line"      # движок честно говорит: ты, вероятно, не прав


def test_minimax_opponent_picks_strongest_counter():
    # у оппонента два ответа; movement должен взять СИЛЬНЕЙШИЙ (min для тебя)
    tree = node(None, [
        node(Move("you", "довод", grounded=True, strength=1.0), [
            node(Move("opponent", "слабый", grounded=True, strength=0.1)),
            node(Move("opponent", "убийственный", grounded=True, strength=0.95)),
        ]),
    ])
    v = evaluate(tree, stance="competitive")
    assert abs(v - (1.0 - 0.95)) < 1e-9   # выбрал 0.95, не 0.1


def test_you_pick_strongest_opening():
    # два твоих захода; берёшь лучший (max)
    tree = node(None, [
        node(Move("you", "слабый заход", grounded=True, strength=0.3)),
        node(Move("you", "сильный заход", grounded=True, strength=0.7)),
    ])
    v = evaluate(tree, stance="competitive")
    assert abs(v - 0.7) < 1e-9


def test_cooperative_stance_rewards_joint_value_not_domination():
    # та же позиция: в competitive ход оппонента ВЫЧИТАЕТСЯ, в cooperative — СКЛАДЫВАЕТСЯ
    tree = node(None, [
        node(Move("you", "тезис", grounded=True, strength=0.5), [
            node(Move("opponent", "встречный вклад", grounded=True, strength=0.4, concession=True)),
        ]),
    ])
    comp = evaluate(tree, stance="competitive")
    coop = evaluate(tree, stance="cooperative")
    assert comp < coop                    # сотрудничество не наказывает вклад другого
    assert verdict(coop, "cooperative")[0] == "synthesis"


def test_principal_variation_returns_best_line():
    tree = node(None, [
        node(Move("you", "плохой", grounded=True, strength=0.2)),
        node(Move("you", "хороший", grounded=True, strength=0.9)),
    ])
    pv = principal_variation(tree, stance="competitive")
    assert [m.claim for m in pv] == ["хороший"]


def test_analyze_bundles_pv_value_and_verdict():
    tree = node(None, [
        node(Move("you", "довод", grounded=True, strength=0.6), [
            node(Move("opponent", "контр", grounded=True, strength=0.3)),
        ]),
    ])
    res = analyze(tree, opponent="person", stance="competitive")
    assert res["value"] > 0
    assert res["verdict"] == "winnable"
    assert [m.claim for m in res["principal_variation"]] == ["довод", "контр"]
    assert res["opponent"] == "person"
