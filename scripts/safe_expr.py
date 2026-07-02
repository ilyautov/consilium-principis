#!/usr/bin/env python3
"""Безопасный компилятор формул карты решения («Principis-расчёт», спека §2).

LLM пишет формулу, юзер визирует, но исполняет её ТОЛЬКО этот модуль — никакого
eval()/exec(): выражение разбирается stdlib `ast.parse`, после чего СТРОГИЙ
whitelist-walker пропускает исключительно:
  • арифметику + - * / и скобки, унарный минус;
  • вызовы min(...) / max(...) (только позиционные аргументы, >= 2);
  • тернарный `a if cond else b` со сравнениями < <= > >= == != (цепочки допустимы);
  • числовые литералы (int/float; bool и строки — НЕ числа, отвергаются);
  • имена ТОЛЬКО из allowed_names (id величин карты).

Всё остальное — атрибуты, сабскрипты, lambda, булевы операторы, степень **,
модуло %, целочисленное //, любые другие вызовы, контейнеры, walrus, f-строки —
отвергается на компиляции (fail-closed). Неизвестный id → ошибка, НЕ ноль (спека §2).

Решения (задокументированы, ревью Ф1):
  • Степень ** НЕ поддерживаем: минимальный белый список; 10**10**10 — DoS-вектор.
  • Литералы обязаны быть КОНЕЧНЫМИ (review C1): `1e999` питон парсит как валидный
    float-Constant со значением inf — такой литерал отвергается на компиляции,
    иначе inf/nan отравил бы «📐 расчёт». Переполнение АРИФМЕТИКИ конечных чисел
    (1e308*1e308 → inf, inf-inf → nan) на компиляции не видно — его ловит mc_run
    по-сценарно (math.isfinite на каждом исходе, второй рубеж).
  • Лимиты: длина выражения <= MAX_EXPR_LEN, глубина AST <= MAX_DEPTH — «огромная
    вложенность» отвергается детерминированно, а не RecursionError где повезёт.
  • Деление на ноль обнаруживается на eval → SafeExprEvalError; вызывающий код
    (mc_run) обязан уронить ВЕСЬ расчёт (fail-closed): формула, делящаяся на ноль
    внутри подтверждённых диапазонов, — дефект модели, юзер должен её починить.
  • Результат коэрсится во float (True/False из верхнеуровневого сравнения → 1.0/0.0).

Ошибки — человеческие RU-строки: хост доносит их до юзера как вопросы совета.
"""
import ast
import math

MAX_EXPR_LEN = 2000   # символов; формулы карты — строки в одну величину-другую
MAX_DEPTH = 50        # глубина AST; честные формулы на порядок мельче


class SafeExprError(ValueError):
    """Ошибка компиляции формулы (запрещённая конструкция / неизвестный id / синтаксис)."""


class SafeExprEvalError(ValueError):
    """Ошибка вычисления формулы (деление на ноль, отсутствующая величина в env)."""


# Разрешённые бинарные операторы → реализация (никакого operator-модуля не нужно,
# но и он stdlib; лямбды прозрачнее для ревью).
_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}

_CMP_OPS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}

_CALLS = {"min": min, "max": max}


def _reject(msg):
    raise SafeExprError(msg)


def _check(node, allowed_names, depth):
    """Whitelist-walker: рекурсивно проверяет узел; всё неперечисленное — отказ."""
    if depth > MAX_DEPTH:
        _reject("Формула слишком глубоко вложена — упростите выражение.")

    if isinstance(node, ast.Expression):
        _check(node.body, allowed_names, depth + 1)
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in _BIN_OPS:
            _reject("В формуле разрешены только операции + - * / — оператор «%s» вне белого списка."
                    % type(node.op).__name__)
        _check(node.left, allowed_names, depth + 1)
        _check(node.right, allowed_names, depth + 1)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.USub):
            _reject("Из унарных операций разрешён только минус.")
        _check(node.operand, allowed_names, depth + 1)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _CALLS:
            _reject("В формуле разрешены только вызовы min(...) и max(...).")
        if node.keywords:
            _reject("min/max в формуле принимают только позиционные аргументы.")
        if any(isinstance(a, ast.Starred) for a in node.args):
            _reject("Распаковка аргументов (*...) в формуле запрещена.")
        if len(node.args) < 2:
            _reject("min/max в формуле требуют минимум два аргумента.")
        for a in node.args:
            _check(a, allowed_names, depth + 1)
    elif isinstance(node, ast.IfExp):
        _check(node.test, allowed_names, depth + 1)
        _check(node.body, allowed_names, depth + 1)
        _check(node.orelse, allowed_names, depth + 1)
    elif isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _CMP_OPS:
                _reject("В сравнениях разрешены только < <= > >= == !=.")
        _check(node.left, allowed_names, depth + 1)
        for c in node.comparators:
            _check(c, allowed_names, depth + 1)
    elif isinstance(node, ast.Name):
        if not isinstance(node.ctx, ast.Load):
            _reject("Присваивания в формуле запрещены.")
        if node.id not in allowed_names:
            _reject("Неизвестная величина «%s» в формуле — каждой величине нужен id из "
                    "uncertainties карты (неизвестный id — отказ, не ноль)." % node.id)
    elif isinstance(node, ast.Constant):
        # bool — подкласс int: проверяем ПЕРВЫМ (True/False — не числа модели)
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            _reject("В формуле разрешены только числовые литералы (не строки, не True/False).")
        try:
            finite = math.isfinite(node.value)
        except OverflowError:
            finite = False   # int-литерал крупнее float-диапазона — тот же яд
        if not finite:
            # 1e999 и подобные питон парсит как float inf — режем (review C1)
            _reject("Числовой литерал в формуле обязан быть конечным числом в разумном "
                    "диапазоне — %.30r… отравил бы расчёт бесконечностью." % node.value)
    else:
        _reject("Конструкция «%s» в формуле запрещена — разрешены только + - * / ( ), "
                "min/max, тернарный if со сравнениями, числа и id величин."
                % type(node).__name__)


def _eval_node(node, env):
    """Вычисление проверенного узла. Только узлы, пропущенные _check."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, env)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        try:
            return _BIN_OPS[type(node.op)](left, right)
        except ZeroDivisionError:
            raise SafeExprEvalError(
                "Деление на ноль при вычислении формулы — проверьте модель: знаменатель "
                "обращается в ноль внутри подтверждённых диапазонов.")
    if isinstance(node, ast.UnaryOp):
        return -_eval_node(node.operand, env)
    if isinstance(node, ast.Call):
        return _CALLS[node.func.id](*[_eval_node(a, env) for a in node.args])
    if isinstance(node, ast.IfExp):
        if _eval_node(node.test, env):
            return _eval_node(node.body, env)
        return _eval_node(node.orelse, env)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval_node(comp, env)
            if not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        try:
            return env[node.id]
        except KeyError:
            raise SafeExprEvalError(
                "Величина «%s» отсутствует в наборе сэмплов — внутренняя ошибка "
                "подстановки, расчёт остановлен (fail-closed)." % node.id)
    if isinstance(node, ast.Constant):
        return node.value
    # недостижимо после _check, но fail-closed на случай рассинхрона walker/eval
    raise SafeExprEvalError("Непроверенный узел «%s» — расчёт остановлен." % type(node).__name__)


def compile_expr(expr, allowed_names):
    """Компилирует формулу в вычислитель fn(env: dict) -> float.

    expr — строка формулы; allowed_names — множество разрешённых id величин.
    Любая запрещённая конструкция / неизвестный id / синтаксическая ошибка →
    SafeExprError (RU-текст). Ошибки вычисления (деление на ноль, дырявый env) →
    SafeExprEvalError из возвращённого вычислителя.
    """
    if not isinstance(expr, str) or not expr.strip():
        raise SafeExprError("Формула пуста или не является строкой — совету нужно "
                            "предложить формулу словами и выражением, юзер визирует.")
    if len(expr) > MAX_EXPR_LEN:
        raise SafeExprError("Формула длиннее %d символов — упростите модель." % MAX_EXPR_LEN)
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise SafeExprError("Формула не разбирается: проверьте синтаксис — разрешены "
                            "только + - * / ( ), min/max, тернарный if со сравнениями, "
                            "числа и id величин.")
    try:
        _check(tree, set(allowed_names), 0)
    except RecursionError:
        raise SafeExprError("Формула слишком глубоко вложена — упростите выражение.")

    def evaluator(env):
        return float(_eval_node(tree, env))

    return evaluator
