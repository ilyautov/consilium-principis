"""Инвариант транспорта: в канал JSON-RPC (fd 1) попадают ТОЛЬКО ответы сервера.

Ревью нашло два пути мусора в канал: print() из фоновой сборки (corpusbuild.*) и дочерние
процессы (pip/ollama pull/collect_pd), наследующие fd 1. И одну кодировочную мину: на Windows
пайп открыт в cp1251, а ответы несут кириллицу и 🔵. Здесь:
  • E2E: реальный сервер подпроцессом с ПОДСАЖЕННЫМ «текущим» тулом (print + дочерний
    процесс, пишущий в stdout) — каждая строка stdout обязана быть валидным JSON-RPC,
    а мусор — оказаться в stderr;
  • юниты stdio_guard: bind_rpc_stdout уводит sys.stdout в stderr и отдаёт UTF-8-поток;
    child_stdout никогда не возвращает наследование fd 1 (None).
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import stdio_guard  # noqa: E402

_LEAKY_SERVER = r'''
import sys, subprocess
sys.path.insert(0, "scripts")
import mcp_server as M
def _leak(text=""):
    print("LEAK-PRINT Кириллица 🔵")                       # тул печатает в stdout
    subprocess.run([sys.executable, "-c", "print('LEAK-CHILD')"],   # ребёнок наследует fd 1
                   stdout=__import__("stdio_guard").child_stdout())
    return {"ok": True, "quote": "Кириллица 🔵", "echo": text}
M.TOOLS["__leak"] = {"handler": _leak, "description": "leak probe",
                     "input_schema": {"type": "object", "properties": {}}}
M.main()
'''


def _req(i, method, **params):
    m = {"jsonrpc": "2.0", "id": i, "method": method}
    if params:
        m["params"] = params
    return json.dumps(m, ensure_ascii=False)


def test_stdout_carries_only_jsonrpc_even_when_tool_and_child_print():
    payload = "\n".join([_req(1, "initialize"), _req(2, "ping"),
                         _req(3, "tools/call", name="__leak"),        # без arguments — по спеке
                         _req(4, "tools/call", name="__leak",
                              arguments={"text": "Из хоста: «ё» и 🟡"})]) + "\n"
    env = {**os.environ, "OLLAMA_HOST": "http://127.0.0.1:59999",
           "PYTHONIOENCODING": "cp1251"}   # эмулируем Windows-пайп: без reconfigure упало бы
    proc = subprocess.run([sys.executable, "-c", _LEAKY_SERVER], input=payload.encode("utf-8"),
                          capture_output=True, cwd=ROOT, env=env, timeout=120)
    out = proc.stdout.decode("utf-8")
    err = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, err
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 4, out
    parsed = [json.loads(ln) for ln in lines]           # КАЖДАЯ строка — валидный JSON-RPC
    assert [p["id"] for p in parsed] == [1, 2, 3, 4]
    assert parsed[1]["result"] == {}                    # ping
    body = json.loads(parsed[2]["result"]["content"][0]["text"])
    assert body["quote"] == "Кириллица 🔵"              # UTF-8 на проводе цел (stdout)
    echo = json.loads(parsed[3]["result"]["content"][0]["text"])["echo"]
    assert echo == "Из хоста: «ё» и 🟡"                   # и на входе (stdin) — не cp1251-каша
    assert "LEAK-PRINT" not in out and "LEAK-CHILD" not in out
    assert "LEAK-PRINT" in err and "LEAK-CHILD" in err  # мусор ушёл в лог хоста


def test_bind_rpc_stdout_redirects_prints_and_returns_utf8_stream(monkeypatch):
    fake_out, fake_err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_out)         # без fileno → ветка «поверх текущего»
    monkeypatch.setattr(sys, "stderr", fake_err)
    rpc = stdio_guard.bind_rpc_stdout()
    print("stray")                                       # любой print после bind → stderr
    assert fake_err.getvalue() == "stray\n"
    assert rpc is fake_out and fake_out.getvalue() == ""


def test_bind_rpc_stdout_dups_real_fd_as_utf8(tmp_path):
    p = tmp_path / "chan.txt"
    with open(p, "w", encoding="utf-8") as f:
        saved_out, saved_err = sys.stdout, sys.stderr
        sys.stdout = f
        try:
            rpc = stdio_guard.bind_rpc_stdout()
            assert rpc is not f and rpc.encoding.lower().replace("-", "") == "utf8"
            assert sys.stdout is saved_err                # print() уходит в stderr
            rpc.write('{"ok":"🔵"}\n')
            rpc.close()
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err
    assert p.read_text(encoding="utf-8") == '{"ok":"🔵"}\n'


def test_child_stdout_never_inherits_fd1(monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())   # pytest-capture без fileno
    assert stdio_guard.child_stdout() is subprocess.DEVNULL
    assert stdio_guard.child_stdout() is not None
