#!/usr/bin/env python3
"""Единый lifecycle сборки доски: build / seed / ingest / doctor / setup-full (H4).

До H4 логика жила в ДВУХ фронтах — board.py CLI и mcp_server.py (_do_*) — и копии
расходились (шаг сборки правился в двух местах). Теперь реализация ОДНА — здесь; оба
фронта зовут эти функции, различия только в презентации (CLI печатает прогресс,
MCP отдаёт dict / крутит фоновый джоб).

Дизайн-решение по write-side path-traversal гарду: гард НЕ переносится и НЕ копируется —
единственная реализация остаётся mcp_server._resolve_under_root (дедуп security-гарда —
смысл рефакторинга, а не его размножение). lifecycle НЕ импортирует mcp_server (тяжёлый
модуль, импорт назад = риск цикличности); вместо этого функции принимают гард КОЛЛБЭКОМ
`resolve_under_root` (dependency injection): MCP-фронт передаёт свой _resolve_under_root
(он резолвит _root() в момент вызова → monkeypatch mcp_server._root в тестах действует),
CLI передаёт None — аргументы CLI даёт сам юзер локально, host-инъекции нет (поведение
board.py сохранено). `root` — тоже параметр с дефолтом corpusbuild.paths.project_root().
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild.paths import project_root  # noqa: E402


def doctor(root=None):
    """Health-check машины: Python, скилл установлен, какой тир (ollama?), самотест рва."""
    from doctor import run_doctor
    return run_doctor(root or project_root())


# do-функции синхронны (их и зовёт board.py CLI без таймаута); тул-обёртки в mcp_server —
# фоновые джобы.
def do_build(advisor_dir, author=None, run_kernels=True, run_index=True, resolve_under_root=None):
    """Советник под ключ: манифест-гейт → corpus → kernels → индекс."""
    from build_orchestrator import build_advisor_full
    if resolve_under_root is not None:
        d, err = resolve_under_root(advisor_dir)         # write-side traversal-гард (host-фронт)
        if err:
            return err
    else:
        d = advisor_dir                                  # CLI: путь от локального юзера, без гарда
    return build_advisor_full(d, author=author,
                              run_kernels=run_kernels, run_index=run_index)


def do_seed(root=None):
    """Стартовый совет PD-мудрецов с нуля (идемпотентно по уже собранным)."""
    from seed import run_seed_council
    return {"results": run_seed_council(root or project_root())}


def do_ingest(handle, out_path=None, root=None, resolve_under_root=None):
    """Публичный Telegram-канал → корпус Принцепса. H1-кламп — на host-фронте (с резолвером)."""
    from ingest_telegram import ingest
    op, error = prepare_ingest_destination(out_path=out_path, root=root,
                                            resolve_under_root=resolve_under_root)
    if error:
        return error
    return ingest(handle, op)


def prepare_ingest_destination(out_path=None, root=None, resolve_under_root=None):
    """Выбрать безопасный новый файл Telegram-корпуса без перезаписи существующего."""
    root = root or project_root()
    if out_path:
        if resolve_under_root is not None:
            op, err = resolve_under_root(out_path)       # write-side traversal-гард
            if err:
                return None, err
            # H1: запись — ТОЛЬКО файл прямо в principis_corpus/ и ТОЛЬКО новый. Иначе
            # out_path=".env" молча уничтожал секреты, а out_path="scripts/mcp_server.py"
            # перезаписывал код сервера (RCE при рестарте) — гард был шире угрозы.
            corpus_dir = os.path.realpath(os.path.join(root, "principis_corpus"))
            if os.path.dirname(op) != corpus_dir:
                return None, {"error": "out_path должен быть новым файлом прямо в principis_corpus/ "
                                        "(запись в код, конфиги и секреты запрещена)."}
            if os.path.exists(op):
                return None, {"error": "файл уже существует — перезапись запрещена: %s" % op}
        else:
            op = out_path                                # CLI: путь от локального юзера
    else:
        corpus_dir = os.path.join(root, "principis_corpus")
        os.makedirs(corpus_dir, exist_ok=True)
        number = 1
        while True:
            name = "telegram.jsonl" if number == 1 else "telegram-%d.jsonl" % number
            op = os.path.join(corpus_dir, name)
            if not os.path.exists(op):
                break
            number += 1
    return op, None


def setup_full(consent=True):
    """Поднять FULL-тир: системный ollama НИКОГДА не ставим молча (вернём инструкцию),
    pull модели bge-m3 — авто при consent. Возвращает шаги + финальный probe()."""
    from setup_full import run_setup
    return run_setup(consent=consent)
