"""Гард единого sys.path-идиома (H3).

Исторически 70+ вставок sys.path.insert по scripts/ в четырёх стилях, до пяти хаков внутри
функций одного модуля (governance.py) — дрейф импортов. Единый идиом:

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # scripts/*.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # подпакеты

Правило гарда: insert — ТОЛЬКО прямой безусловный statement верхнего уровня модуля и ДО
первого def/class. Не внутри функций, не под if/try/for, не после определений.

Почему AST, а не «первые 15 строк» из брифа: у части модулей docstring сам длиннее любого
фиксированного окна (governance.py — 36 строк, mcp_server.py — 25, bootstrap_eval.py —
21 + from __future__); даже самая ранняя легальная позиция insert'а там за его пределами.
AST кодирует сам инвариант («верх модуля, без условий») без магических чисел.
"""
import ast
import os

# Осознанных исключений нет: все sys.path.insert — прямые безусловные statements наверху модуля.
_ALLOWED_LAZY = {}


def _is_syspath_insert(node):
    """Call вида (sys|_sys).path.insert(...)?"""
    f = getattr(node, "func", None)
    return (isinstance(node, ast.Call)
            and isinstance(f, ast.Attribute) and f.attr == "insert"
            and isinstance(f.value, ast.Attribute) and f.value.attr == "path"
            and isinstance(f.value.value, ast.Name)
            and f.value.value.id in ("sys", "_sys"))


def test_no_infunction_syspath_hacks():
    root = os.path.join(os.path.dirname(__file__), "..", "scripts")
    bad = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            with open(p, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=rel)
            direct = {id(s.value) for s in tree.body if isinstance(s, ast.Expr)}
            first_def = min((s.lineno for s in tree.body
                             if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef,
                                               ast.ClassDef))), default=10 ** 9)
            nested = []
            for node in ast.walk(tree):
                if not _is_syspath_insert(node):
                    continue
                if id(node) not in direct:
                    nested.append(node.lineno)
                elif node.lineno > first_def:
                    bad.append("%s:%d — insert после первого def/class (идиом — верх модуля)"
                               % (rel, node.lineno))
            for ln in nested[_ALLOWED_LAZY.get(rel, 0):]:
                bad.append("%s:%d — in-function/conditional sys.path.insert "
                           "(идиом — прямой безусловный statement наверху модуля)" % (rel, ln))
    assert not bad, "sys.path.insert вне единого идиома:\n" + "\n".join(sorted(bad))
