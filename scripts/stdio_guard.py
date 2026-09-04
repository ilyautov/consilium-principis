#!/usr/bin/env python3
"""Изоляция JSON-RPC-канала MCP-сервера от stdout и от кодировки локали.

Транспорт MCP по stdio — построчный JSON на fd 1. Всё, что попадает туда помимо ответов
сервера, ломает канал у хоста (Claude Desktop/Code молча роняют сервер на не-JSON строке).
Источники мусора, найденные ревью:
  • print() из фоновой сборки советника (corpusbuild.* печатал прогресс в stdout);
  • дочерние процессы (pip install numpy, ollama pull, collect_pd.py) наследовали fd 1.
Кодировка: на Windows stdout/stdin пайпа открыты в ANSI (cp1251/cp1252), а ответы несут
кириллицу и 🔵/🟡 → UnicodeEncodeError на первом же ответе либо тихая порча цитаты на входе
(и ложный 🟡). PYTHONUTF8 ставил только install.bat на время установки.

Контракт:
  bind_rpc_stdout() → текстовый поток на ДУБЛИКАТЕ fd 1 (UTF-8, '\\n', построчный flush);
                      sys.stdout перенаправлен в sys.stderr — любой print() уходит в лог хоста.
  bind_rpc_stdin()  → sys.stdin в UTF-8 (errors=replace: битый байт не роняет цикл).
  child_stdout()    → куда слать stdout дочернего процесса: stderr сервера (есть fd) или
                      DEVNULL (pytest-capture). Никогда — наследовать fd 1.
"""
import io
import os
import subprocess
import sys


def _reconfigure_utf8(stream):
    rc = getattr(stream, "reconfigure", None)
    if rc is None:
        return
    try:
        rc(encoding="utf-8", errors="replace")
    except (ValueError, OSError, io.UnsupportedOperation):
        pass                                   # закрытый/нестандартный поток — оставляем как есть


def bind_rpc_stdout():
    """Отвязать writer протокола от sys.stdout. Возвращает поток для ответов JSON-RPC."""
    try:
        fd = os.dup(sys.stdout.fileno())
        out = os.fdopen(fd, "w", encoding="utf-8", errors="replace", newline="\n", buffering=1)
    except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
        out = sys.stdout                       # нет реального fd (встраивание/тесты) — поверх текущего
        _reconfigure_utf8(out)
    sys.stdout = sys.stderr                    # print() тулов/сборки → лог, не канал
    return out


def bind_rpc_stdin():
    """stdin протокола в UTF-8 независимо от локали ОС."""
    _reconfigure_utf8(sys.stdin)
    return sys.stdin


def child_stdout():
    """stdout для subprocess.run(...) внутри сервера: stderr сервера, иначе DEVNULL."""
    try:
        sys.stderr.fileno()
        return sys.stderr
    except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
        return subprocess.DEVNULL
