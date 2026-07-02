"""Безопасный компилятор формул карты решения — тесты.

Стерегут два инварианта Ф1 («Principis-расчёт», спека §2):
  • ВЫРАЗИМОСТЬ: + - * / ( ), унарный минус, min/max, тернарный if со сравнениями,
    числовые литералы, id величин — всё компилируется и считает верно.
  • FAIL-CLOSED: всё вне белого списка отвергается на компиляции (import, атрибуты,
    сабскрипты, lambda, booleans, **, вызовы кроме min/max, неизвестные id — ошибка,
    НЕ ноль). Деление на ноль — ошибка на eval (SafeExprEvalError), не NaN/inf.
Никакого eval(), никакой сети — чистый stdlib ast.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from safe_expr import SafeExprError, SafeExprEvalError, compile_expr

ALLOWED = {"x", "y", "prob_a"}


def _ev(expr, env=None, allowed=ALLOWED):
    fn = compile_expr(expr, allowed)
    return fn(env or {})


# ── выразимость: то, что ДОЛЖНО работать ────────────────────────────────────

def test_arithmetic_basic():
    assert _ev("2 + 3 * 4 - 1") == 13.0
    assert _ev("(2 + 3) * 4") == 20.0
    assert _ev("10 / 4") == 2.5


def test_unary_minus():
    assert _ev("-5 + 3") == -2.0
    assert _ev("-(2 + 3)") == -5.0
    assert _ev("--4") == 4.0


def test_variables_from_env():
    assert _ev("x * y - 3", {"x": 2.0, "y": 5.0}) == 7.0


def test_min_max():
    assert _ev("min(3, 7)") == 3.0
    assert _ev("max(3, 7, 1)") == 7.0
    assert _ev("min(x, 0) + max(y, 10)", {"x": -4.0, "y": 2.0}) == 6.0


def test_ternary_and_comparisons():
    assert _ev("1 if x > 0 else 2", {"x": 5.0}) == 1.0
    assert _ev("1 if x > 0 else 2", {"x": -5.0}) == 2.0
    assert _ev("x if x >= y else y", {"x": 3.0, "y": 8.0}) == 8.0
    assert _ev("7 if x == 1 else 9", {"x": 1.0}) == 7.0
    assert _ev("7 if x != 1 else 9", {"x": 1.0}) == 9.0
    assert _ev("1 if x < 2 else 0", {"x": 1.0}) == 1.0
    assert _ev("1 if x <= 1 else 0", {"x": 1.0}) == 1.0


def test_comparison_chain():
    # цепочка сравнений безопасна и поддерживается (python-семантика)
    assert _ev("1 if 0 < x < 10 else 0", {"x": 5.0}) == 1.0
    assert _ev("1 if 0 < x < 10 else 0", {"x": 15.0}) == 0.0


def test_float_literals():
    assert _ev("0.3 * 100") == pytest.approx(30.0)


def test_result_is_float():
    assert isinstance(_ev("1 + 1"), float)


def test_realistic_map_formula():
    # формула из спеки: traction_prob * upside_hours - hours_to_ship
    allowed = {"traction_prob", "upside_hours", "hours_to_ship"}
    env = {"traction_prob": 1.0, "upside_hours": 150.0, "hours_to_ship": 40.0}
    assert _ev("traction_prob * upside_hours - hours_to_ship", env, allowed) == 110.0


# ── fail-closed: неизвестные id ─────────────────────────────────────────────

def test_unknown_id_is_error_not_zero():
    with pytest.raises(SafeExprError) as e:
        compile_expr("x + zzz_unknown", ALLOWED)
    assert "zzz_unknown" in str(e.value)


def test_empty_allowed_rejects_any_name():
    with pytest.raises(SafeExprError):
        compile_expr("x", set())


# ── fail-closed: атаки и запрещённые конструкции ────────────────────────────

@pytest.mark.parametrize("attack", [
    "__import__('os').system('id')",
    "().__class__.__bases__[0]",
    "x.__class__",
    "x.real",              # доступ к атрибутам запрещён целиком
    "x[0]",                # сабскрипт
    "(lambda: 1)()",       # lambda
    "lambda: 1",
    "x and y",             # булевы операторы вне белого списка
    "x or y",
    "not x",
    "2 ** 10",             # степень намеренно не поддерживаем
    "7 % 3",               # модуло вне белого списка
    "7 // 2",              # целочисленное деление вне белого списка
    "abs(x)",              # вызовы только min/max
    "eval('1')",
    "min(x, key=abs)",     # keyword-аргументы запрещены
    "min(*[1, 2])",        # starred-аргументы запрещены
    "min([1, 2])",         # контейнеры запрещены
    "max({'a': 1})",
    "'строка'",            # строковый литерал — не число
    "True",                # bool-литерал — не число (fail-closed)
    "None",
    "x if x else __import__('os')",
    "[1, 2]",
    "{1: 2}",
    "(1, 2)",
    "f'{x}'",
    "x := 1",
])
def test_attacks_rejected(attack):
    with pytest.raises(SafeExprError):
        compile_expr(attack, ALLOWED)


def test_statements_rejected():
    with pytest.raises(SafeExprError):
        compile_expr("import os", ALLOWED)
    with pytest.raises(SafeExprError):
        compile_expr("1; 2", ALLOWED)


def test_huge_nesting_rejected():
    deep = "(" * 500 + "1" + ")" * 500
    with pytest.raises(SafeExprError):
        compile_expr(deep, ALLOWED)


def test_huge_expression_rejected():
    with pytest.raises(SafeExprError):
        compile_expr("1 + " * 5000 + "1", ALLOWED)


def test_empty_and_garbage_rejected():
    for bad in ("", "   ", "+", "x +", "((1)", None, 42):
        with pytest.raises(SafeExprError):
            compile_expr(bad, ALLOWED)


def test_min_max_arity():
    # min/max минимум с двумя аргументами (скалярная семантика)
    with pytest.raises(SafeExprError):
        compile_expr("min(x)", ALLOWED)
    with pytest.raises(SafeExprError):
        compile_expr("max()", ALLOWED)


def test_error_messages_are_russian_strings():
    with pytest.raises(SafeExprError) as e:
        compile_expr("x.__class__", ALLOWED)
    msg = str(e.value)
    assert isinstance(msg, str) and len(msg) > 0
    # человеческая формулировка — кириллица присутствует
    assert any("а" <= ch <= "я" or ch == "ё" for ch in msg.lower())


# ── деление на ноль: ошибка на eval, не NaN ─────────────────────────────────

def test_division_by_zero_raises_eval_error():
    fn = compile_expr("1 / x", ALLOWED)
    with pytest.raises(SafeExprEvalError):
        fn({"x": 0.0})
    # с ненулевым x — работает
    assert fn({"x": 2.0}) == 0.5


def test_env_missing_id_raises_eval_error():
    # компиляция разрешила id, но env его не дал — fail-closed на eval
    fn = compile_expr("x + y", ALLOWED)
    with pytest.raises(SafeExprEvalError):
        fn({"x": 1.0})
