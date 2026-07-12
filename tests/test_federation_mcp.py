"""MCP-проводка федерации: 6 тулов через TOOLS + централизованный гейт инъектится в assemble."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import mcp_server as m


def test_federation_tools_registered():
    for name in ("federation_open", "federation_poll", "federation_assemble",
                 "federation_claim", "federation_submit", "federation_heartbeat"):
        assert name in m.TOOLS, name
        assert "handler" in m.TOOLS[name] and "input_schema" in m.TOOLS[name]


def test_federation_open_poll_dispatch_roundtrip(tmp_path, monkeypatch):
    # изолируем стейт федерации во временную папку
    monkeypatch.setattr(m, "_fed_backend", lambda: m._make_fed_backend(str(tmp_path / "f.sqlite3")))
    plan = [{"role": "aurelius", "advisor_dir": "advisors/aurelius", "question": "Q", "replicas": 2}]
    r = m.dispatch("federation_open", {"session_id": "s1", "plan": plan})
    assert r["enqueued"] == 2
    p = m.dispatch("federation_poll", {"session_id": "s1"})
    assert p["pending"] == 2


def test_federation_claim_submit_assemble_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_fed_backend", lambda: m._make_fed_backend(str(tmp_path / "f2.sqlite3")))
    # верность мокаем детерминированно, чтобы не зависеть от корпуса
    monkeypatch.setattr(m, "_fidelity_check",
                        lambda quote, advisor_dir: {"status": "🔵", "verbatim": True, "source": "S"}
                        if quote == "REAL" else {"status": "🟡", "verbatim": False, "source": ""})
    m.dispatch("federation_open", {"session_id": "s1",
               "plan": [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                         "question": "Q", "replicas": 1}]})
    brief = m.dispatch("federation_claim", {"worker_id": "w1", "roles": ["aurelius"], "timeout": 1.0})
    assert brief["role"] == "aurelius"
    sub = m.dispatch("federation_submit", {"task_id": brief["task_id"], "worker_id": "w1",
                     "claim_token": brief["claim_token"], "worker_model": "claude-sonnet-5",
                     "candidate": {"argument": "keep calm", "quotes": [{"text": "REAL"}]}})
    assert sub["ok"] is True
    out = m.dispatch("federation_assemble", {"session_id": "s1"})
    role0 = out["roles"][0]
    assert role0["representative"]["quotes"][0]["status"] == "🔵"   # сервер-сверка через _fidelity_check
    assert role0["worker_models"] == ["claude-sonnet-5"]
