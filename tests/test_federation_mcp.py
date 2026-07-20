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


def test_federation_open_caps_plan_and_replicas(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(m, "_FED_BACKEND", None)
    out = m.dispatch("federation_open",
                     {"session_id": "s1",
                      "plan": [{"role": "r%d" % i} for i in range(500)]})
    assert "error" in out
    # replicas_default без потолка → кламп к 32 на роль (иначе 1e9 INSERT'ов в sqlite)
    out = m.dispatch("federation_open",
                     {"session_id": "s2",
                      "plan": [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                                "question": "Q"}],
                      "replicas_default": 100})
    assert out["enqueued"] <= 32


def test_federation_open_caps_per_item_replicas(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_fed_backend", lambda: m._make_fed_backend(str(tmp_path / "f.sqlite3")))
    item = {"role": "x", "advisor_dir": "advisors/x", "question": "Q"}
    # per-item replicas без потолка обходил кап дефолта (M2-follow) → кламп к 32
    out = m.dispatch("federation_open", {"session_id": "s1", "plan": [dict(item, replicas=2000)]})
    assert out["enqueued"] <= 32
    # мусор в per-item replicas → фолбэк на replicas_default, без сырого исключения
    out = m.dispatch("federation_open", {"session_id": "s2", "plan": [dict(item, replicas="junk")],
                                         "replicas_default": 2})
    assert out["enqueued"] == 2
    # регресс-контроль: легитимный per-item replicas доезжает как был
    out = m.dispatch("federation_open", {"session_id": "s3", "plan": [dict(item, replicas=2)]})
    assert out["enqueued"] == 2


def test_federation_open_rejects_non_dict_item(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_fed_backend", lambda: m._make_fed_backend(str(tmp_path / "f.sqlite3")))
    out = m.dispatch("federation_open", {"session_id": "s1", "plan": ["not-a-dict"]})
    assert "error" in out


def test_federation_claim_timeout_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(m, "_FED_BACKEND", None)
    # timeout=10**9 не должен блокировать RPC-цикл: кламп к 60с — проверяем кламп, не сон.
    seen = {}
    def spy(backend, worker_id, roles, timeout):
        seen["timeout"] = timeout
        return {"tasks": []}
    monkeypatch.setattr(m, "_fed_claim", spy)
    m.dispatch("federation_claim", {"worker_id": "w", "timeout": 10**9})
    assert seen["timeout"] <= 60.0
