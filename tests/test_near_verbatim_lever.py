"""Рычаг near-verbatim: формулируй запрос как ЗВУЧАЛА БЫ ЦИТАТА, а не как тему (слой 2).

Основание — замер, а не вкус (scripts/experiments/results/tier-pool-2026-07-15.json):
парный градиент стиля на golden от 25 июня (literal/abstract на ОДИН якорь, конфаунды
сокращаются) даёт Δanchor-recall +0.267 / ΔMRR +0.150 — попаданий в нужный пассаж ВПЯТЕРО
больше (machiavelli: 0.333 против 0.067). Это единственный рычаг с доказанным эффектом:
квота (слой 4) отменена эмпирически — пул Макиавелли УЖЕ на 74% первоисточник и 🔵-кандидат
есть у каждого запроса, а Сунь-Цзы держит идеальный ретрив при 🔵share 0.375.

Механизм (почему это работает, а не магия): тематический запрос ловит того, кто пишет о
предмете ПРЯМЫМ ТЕКСТОМ — то есть комментатора. Советник говорит косвенно и метафорично,
поэтому его достаёт запрос, похожий на саму цитату.

Гард синхронности: рычаг обязан жить на ВСЕХ трёх поверхностях. Хост читает INSTRUCTIONS,
но описание тула и note возвращаются в точке использования — расхождение = хост получит
разный совет в зависимости от того, куда посмотрит. Дрейф одной поверхности при правке
других — реальный класс дефекта в этом проекте (ср. test_no_dark_tools: 4 канала).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server  # noqa: E402


def _instructions():
    return mcp_server.INSTRUCTIONS


def test_instructions_carry_near_verbatim_lever():
    t = _instructions().lower()
    assert "звучала бы" in t or "как сама цитата" in t, \
        "Rule 5 не учит формулировать запрос как цитату — рычаг с доказанным 5× эффектом потерян"


def test_instructions_explain_the_mechanism_not_just_the_rule():
    """Правило без «почему» хост применит буквально и не обобщит на новый корпус."""
    t = _instructions().lower()
    assert "комментатор" in t or "прямым текстом" in t, \
        "не объяснено, ПОЧЕМУ тема ловит вторичку → правило не обобщается"


def test_cite_tool_description_carries_lever():
    d = mcp_server.TOOLS["cite"]["description"].lower()
    assert "звучала бы" in d or "как сама цитата" in d, \
        "описание тула cite молчит про near-verbatim — точка использования рассинхронизирована"


def test_cite_note_carries_lever_when_quotes_found():
    out = mcp_server._cite_result(
        [{"text": "safer to be feared than loved", "source": "prince.txt", "marker": "🔵"}], {})
    assert "звучала бы" in out["note"].lower() or "как сама цитата" in out["note"].lower(), \
        "note при находке не подсказывает, КАК спрашивать лучше в следующий раз"


def test_cite_note_carries_lever_when_empty():
    """Пустой результат — момент, когда подсказка нужнее всего: хост сейчас пойдёт в 🟡."""
    out = mcp_server._cite_result([], {})
    n = out["note"].lower()
    assert "звучала бы" in n or "как сама цитата" in n, \
        "пустой cite не учит переформулировать — хост уйдёт в 🟡, хотя цитата в корпусе есть"
    assert "не выдумывай" in n, "fail-closed нельзя размывать подсказкой про рекол"


def test_lever_does_not_promise_a_gate_bypass():
    """Рычаг про RECALL, а не про ров: переформулировка не делает 🔵 из недословного."""
    n = mcp_server._cite_result([], {})["note"].lower()
    assert "гейт исправен" in n, "подсказка не должна намекать, что 🟡 = поломка гейта"
