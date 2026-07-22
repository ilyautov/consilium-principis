"""E2E построчного stdio-цикла MCP-сервера (_serve_stdio) — последнее слепое пятно главного файла.

Гоняем РЕАЛЬНЫЙ цикл на подменённых sys.stdin/sys.stdout (io.StringIO, без подпроцесса):
  • oversized-строка (> _MAX_LINE) → хвост дренируется чанками, ответ -32600 с id=null,
    цикл НЕ ломается и следующая валидная строка обслуживается;
  • битая JSON-строка → молча пропускается, цикл продолжается;
  • notification (без id) → ответа НЕТ (ни на notifications/initialized, ни на мусорный method);
  • EOF → чистый выход.
Гермётично: stdin/stdout восстанавливает monkeypatch, диска/сети нет.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import mcp_server as M


def _run_stdio(monkeypatch, payload):
    """Прогон _serve_stdio на строке-входе. Возвращает список распарсенных ответов."""
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(sys, "stdout", out)
    M._serve_stdio()                          # выходит по EOF StringIO
    return [json.loads(ln) for ln in out.getvalue().splitlines() if ln.strip()]


def _req(method, req_id=1, **params):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        msg["params"] = params
    return json.dumps(msg)


def test_oversized_line_drains_and_replies_32600_null_id(monkeypatch):
    """Строка за капом: дренаж хвоста, -32600 с id=null — и цикл жив: следующая строка обслужена."""
    oversized = "x" * (M._MAX_LINE + 4096) + "\n"          # перерост в средине строки (без '\n')
    payload = oversized + _req("initialize", req_id=1) + "\n"
    responses = _run_stdio(monkeypatch, payload)
    assert len(responses) == 2                             # ошибка + ответ на initialize
    err = responses[0]
    assert err["id"] is None                               # id=null: запрос не парсили, id неизвестен
    assert err["error"]["code"] == -32600
    ok = responses[1]
    assert ok["id"] == 1 and ok["result"]["serverInfo"]["name"] == "consilium-principis"


def test_oversized_line_exactly_at_cap_is_processed(monkeypatch):
    """Регресс-контроль границы: строка ровно в капе НЕ отвергается (валидный JSON обслуживается)."""
    pad = M._MAX_LINE - len(_req("initialize", req_id=2)) - 1
    # добиваем валидный JSON пробелами ровно до капа (json парсит trailing spaces)
    line = _req("initialize", req_id=2) + " " * pad + "\n"
    assert len(line) <= M._MAX_LINE
    responses = _run_stdio(monkeypatch, line)
    assert len(responses) == 1 and responses[0]["id"] == 2 and "result" in responses[0]


def test_broken_json_line_returns_parse_error_and_loop_continues(monkeypatch):
    """Битая JSON-строка даёт JSON-RPC parse error; следующие строки обслуживаются."""
    payload = ("это не json совсем\n"
               "\n"                                        # пустая строка — тоже пропуск
               "{\"jsonrpc\": \"2.0\", \"id\": 5, \n"      # оборванный JSON
               + _req("tools/list", req_id=7) + "\n")
    responses = _run_stdio(monkeypatch, payload)
    assert len(responses) == 3
    assert all(response["error"]["code"] == -32700 for response in responses[:2])
    assert responses[2]["id"] == 7 and "tools" in responses[2]["result"]


def test_stdio_recovers_after_non_object_requests_then_initializes(monkeypatch):
    """null и массив не роняют поле-доступ и получают Invalid Request."""
    payload = "null\n[]\n" + _req("initialize", req_id=8) + "\n"
    responses = _run_stdio(monkeypatch, payload)
    assert [response["error"]["code"] for response in responses[:2]] == [-32600, -32600]
    assert responses[2]["result"]["serverInfo"]["name"] == "consilium-principis"


def test_tools_call_rejects_non_object_params_and_arguments():
    """tools/call принимает только JSON-объекты params и arguments."""
    for params in ([], "bad", 1, {"name": "doctor"}, {"name": "doctor", "arguments": []}):
        response = M._handle_rpc({"jsonrpc": "2.0", "id": 9,
                                  "method": "tools/call", "params": params})
        assert response["error"]["code"] == -32602


def test_notification_gets_no_response(monkeypatch):
    """Нотификации (без id) не отвечаются: ни initialized, ни неизвестный method. EOF — выход."""
    payload = (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
               + json.dumps({"jsonrpc": "2.0", "method": "no/such/method"}) + "\n")
    assert _run_stdio(monkeypatch, payload) == []


def test_eof_terminates_cleanly(monkeypatch):
    """Пустой вход → цикл завершается по EOF молча (не висит, не падает)."""
    assert _run_stdio(monkeypatch, "") == []
