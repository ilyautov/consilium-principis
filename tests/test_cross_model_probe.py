"""Офлайн-тест машинерии cross-model probe: mock host/other/judge, проверяем A/B + статистику."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "experiments"))
import cross_model_probe as P  # noqa: E402


TINY = [
    {"id": "a", "category": "factual_trap", "question": "Столица Австралии?", "trap": "Сидней вместо Канберры"},
    {"id": "b", "category": "reasoning_trap", "question": "Мяч и бита $1.10?", "trap": "10 вместо 5 центов"},
    {"id": "c", "category": "consensus_trap", "question": "Поднимать VC рано?", "trap": "сходится к да"},
]


def _host(prompt):
    return "HOST: обычный усреднённый ответ."


def _other(prompt):
    return "OTHER: указывает на ловушку, которую хост пропустил."


def _judge_high(prompt):
    # cross_model место реально ловит → высокие оси. Детерминированно возвращаем 3.
    return "3"


def test_run_conditions_wire_cross_seat():
    rows_a = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    rows_b = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    # В A ни одно место не OTHER; в B ровно место CROSS_SEAT_INDEX — OTHER.
    assert all("OTHER:" not in r["answer"] for r in rows_a)
    assert all("OTHER:" in r["answer"] for r in rows_b)


def test_unknown_condition_raises():
    import pytest
    with pytest.raises(ValueError):
        P.run("bogus", battery=TINY, call_host=_host, call_other=_other)


def test_compare_produces_axes_ci_signal():
    rows_a = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    rows_b = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    by_a = {r["id"]: r for r in rows_a}
    scen = {r["id"]: r for r in TINY}
    for rb in rows_b:
        rb["axes"] = P.judge_pair(by_a[rb["id"]], rb, scen[rb["id"]], call=_judge_high)
    for ra in rows_a:
        ra["axes"] = {axis: None for axis in P._AXIS_NAMES}
    result = P.compare(rows_b, rows_a)
    for axis in P._AXIS_NAMES:
        c = result["overall"][axis]
        assert c["mean"] == 1.0  # все судьи вернули 3 → 3/3
        assert c["n"] == 3
        assert c["ci"] is not None and c["n_ci"] == 3
        assert c["signal"] is True  # CI на константе 1.0 не включает 0


def test_judge_none_safe_on_missing_answer():
    axes = P.judge_pair({"answer": None}, {"answer": "x"}, TINY[0], call=_judge_high)
    assert all(v is None for v in axes.values())


def test_determinism_same_seed_same_ci():
    def score(rows_a, rows_b):
        by_a = {r["id"]: r for r in rows_a}
        scen = {r["id"]: r for r in TINY}
        for rb in rows_b:
            rb["axes"] = P.judge_pair(by_a[rb["id"]], rb, scen[rb["id"]], call=_judge_high)
        for ra in rows_a:
            ra["axes"] = {axis: None for axis in P._AXIS_NAMES}
        return P.compare(rows_b, rows_a)["overall"]["blindspot_catch"]["ci"]
    a1 = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    b1 = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    a2 = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    b2 = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    assert score(a1, b1) == score(a2, b2)
