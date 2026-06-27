#!/usr/bin/env python3
"""Глубокая ситуационная карта — один движок для трёх фич (синтез сессии 2026-06-28).

Решение, спор и действие-в-мире — ОДНА ситуация: ты + оппонент. Меняется лишь кто напротив:
  • оппонент = ты      → бизнес/личное РЕШЕНИЕ (внутренний оппонент: заявленное «я» vs выбираемое);
  • оппонент = человек → СПОР (стратегичен: адаптируется, блефует, защищает лицо);
  • оппонент = мир     → ДЕЙСТВИЕ/прогноз (без умысла, но с динамикой).
Верхний параметр — СТОЙКА: competitive (перевес над оппонентом) | cooperative (совместная ценность;
не всякая ситуация zero-sum — спор бывает совместным поиском истины, мир тебе не мстит).

`analyze()` строит КАРТУ ситуации: дерево возможных путей, сильнейшие контрмеры оппонента,
главную линию (principal variation) и ЧЕСТНЫЙ вердикт. Это не «умный ответ», а как шахматный
движок: показывает и +5, и −5. Инварианты ядра:
  • контур — нельзя выиграть ФАБРИКАЦИЕЙ: необоснованный ход (grounded=False) даёт 0 силы;
  • честность — нет выигрышной линии → движок ГОВОРИТ это (ты, вероятно, не прав);
  • minimax — оппонент играет СИЛЬНЕЙШУЮ контрмеру.

Это ЧИСТОЕ ядро (дерево уже построено). Генерация ходов советниками/линзами (LLM) — слой поверх:
советники = генераторы ходов в своём стиле, контур-гейт = оценка обоснованности хода.
"""


class Move:
    """Ход в ситуации. grounded по умолчанию False — ход считается блефом, пока не доказан
    (fail-closed). strength — сила довода ∈ [0,1]. concession — уступка/совместный вклад."""
    def __init__(self, by, claim, grounded=False, strength=0.0, concession=False):
        assert by in ("you", "opponent")
        self.by = by
        self.claim = claim
        self.grounded = grounded
        self.strength = strength
        self.concession = concession

    def __repr__(self):
        g = "🔵" if self.grounded else "🟡"
        return f"Move({self.by} {g} {self.strength}: {self.claim!r})"


def node(move, children=None):
    """Узел дерева ситуации: ход + ответные ходы. move=None у корня."""
    return {"move": move, "children": children or []}


def _contribution(move, stance):
    """Вклад хода в оценку. Контур: необоснованный ход (grounded=False) → 0 (фабрикацией
    не выигрывают). competitive: твой ход +, оппонента −. cooperative: любой обоснованный +."""
    if move is None:
        return 0.0
    s = move.strength if move.grounded else 0.0
    if stance == "cooperative":
        return s
    return s if move.by == "you" else -s


def _best_index(children, stance):
    """Индекс ребёнка, который движок выберет. cooperative → max совместной ценности.
    competitive → твой ход максимизируешь ТЫ (max), ход оппонента он играет СИЛЬНЕЙШИЙ (min)."""
    vals = [evaluate(c, stance) for c in children]
    if stance == "cooperative" or children[0]["move"].by == "you":
        return vals.index(max(vals))
    return vals.index(min(vals))           # оппонент минимизирует твою оценку


def evaluate(tree, stance="competitive"):
    """Minimax-оценка позиции. >0 (competitive) = у тебя есть перевес."""
    contrib = _contribution(tree["move"], stance)
    children = tree["children"]
    if not children:
        return contrib
    return contrib + evaluate(children[_best_index(children, stance)], stance)


def principal_variation(tree, stance="competitive"):
    """Главная линия — последовательность ходов по лучшему выбору на каждом уровне."""
    head = [tree["move"]] if tree["move"] is not None else []
    children = tree["children"]
    if not children:
        return head
    return head + principal_variation(children[_best_index(children, stance)], stance)


def verdict(value, stance):
    """Честный вердикт. cooperative → ('synthesis', value). competitive: перевес есть →
    'winnable', иначе 'no_winning_line' (движок не льстит: линии нет — ты, вероятно, не прав)."""
    if stance == "cooperative":
        return ("synthesis", value)
    if value > 0:
        return ("winnable", value)
    return ("no_winning_line", value)


def analyze(tree, opponent="person", stance="competitive"):
    """Ситуационная карта: оценка + главная линия + честный вердикт + кто оппонент.

    opponent ∈ {'self','person','world'} — параметр модели оппонента (eval-нюансы — слой выше:
    self=растворить рассогласование, person=линия держится, world=одобренный позже исход)."""
    value = evaluate(tree, stance)
    return {
        "opponent": opponent,
        "stance": stance,
        "value": value,
        "verdict": verdict(value, stance)[0],
        "principal_variation": principal_variation(tree, stance),
    }
