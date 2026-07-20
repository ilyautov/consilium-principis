"""MCP-проводка федерации: 6 тулов через TOOLS + централизованный гейт инъектится в assemble."""
import json
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


def test_federation_open_rejects_oversize_field_before_backend(tmp_path, monkeypatch):
    backend = m._make_fed_backend(str(tmp_path / "f.sqlite3"))
    calls = []

    def backend_spy():
        calls.append(True)
        return backend

    monkeypatch.setattr(m, "_fed_backend", backend_spy)
    out = m.dispatch("federation_open", {"session_id": "s1", "plan": [{
        "role": "role", "advisor_dir": "advisors/a", "question": "q" * 4097,
    }]})
    assert "error" in out
    assert calls == []


def test_federation_open_rejects_oversize_expanded_questions_before_backend(tmp_path, monkeypatch):
    backend = m._make_fed_backend(str(tmp_path / "f.sqlite3"))
    calls = []

    def backend_spy():
        calls.append(True)
        return backend

    monkeypatch.setattr(m, "_fed_backend", backend_spy)
    plan = [{"role": "role%d" % i, "advisor_dir": "advisors/a%d" % i,
             "question": "q" * 4096, "replicas": 32}
            for i in range(3)]
    out = m.dispatch("federation_open", {"session_id": "s1", "plan": plan})
    assert "error" in out
    assert calls == []


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


def test_federation_full_cycle_open_claim_submit_poll_assemble(tmp_path, monkeypatch):
    """Сквозной e2e на ЖИВОМ sqlite-бэкенде: _root → tmp (стейт пишется в tmp/.consilium/),
    _FED_BACKEND сброшен → _fed_backend() сам строит SqliteBackend, как в проде. Верность
    сверяет НАСТОЯЩИЙ _fidelity_check против синтетического tmp-корпуса (не мок)."""
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(m, "_FED_BACKEND", None)
    real_quote = "Waste no more time arguing what a good man should be. Be one."
    fake_quote = "выдуманная строка, которой заведомо нет ни в одном корпусе"
    adv = tmp_path / "advisors" / "marcus-aurelius" / "build"
    adv.mkdir(parents=True)
    (adv / "corpus.jsonl").write_text(
        json.dumps({"text": real_quote + " " + "Filler sentence for the chunk body.",
                    "source": "meditations.txt", "tier": "P1"}, ensure_ascii=False) + "\n",
        encoding="utf-8")

    plan = [{"role": "стоик", "advisor_dir": "advisors/marcus-aurelius",
             "question": "Как жить?", "replicas": 1},
            {"role": "тактик", "advisor_dir": "advisors/machiavelli",
             "question": "Как жить?", "replicas": 1}]
    opened = m.dispatch("federation_open", {"session_id": "e2e", "plan": plan})
    assert opened["enqueued"] == 2
    assert m.dispatch("federation_poll", {"session_id": "e2e"})["pending"] == 2

    brief = m.dispatch("federation_claim", {"worker_id": "w1", "roles": ["стоик"], "timeout": 1.0})
    assert brief["role"] == "стоик" and brief["question"] == "Как жить?"
    sub = m.dispatch("federation_submit", {
        "task_id": brief["task_id"], "worker_id": "w1", "claim_token": brief["claim_token"],
        "worker_model": "model-A",
        "candidate": {"argument": "Действуй, не рассуждай.",
                      "quotes": [{"text": real_quote}, {"text": fake_quote}]}})
    assert sub == {"ok": True}
    mid = m.dispatch("federation_poll", {"session_id": "e2e"})
    assert mid["done"] == 1 and mid["pending"] == 1

    out = m.dispatch("federation_assemble", {"session_id": "e2e"})
    assert out["session_id"] == "e2e"
    by_role = {r["role"]: r for r in out["roles"]}
    stoa = by_role["стоик"]
    assert stoa["representative"]["worker_model"] == "model-A"
    statuses = {q["text"]: q["status"] for q in stoa["representative"]["quotes"]}
    assert statuses[real_quote] == "🔵"              # живая сверка против tmp-корпуса
    assert statuses[fake_quote] == "🟡"              # выдумка честно не подтверждена
    assert stoa["grounded_replicas"] == 1
    assert stoa["replicas_done"] == 1 and stoa["replicas_total"] == 1 and stoa["complete"] is True
    # несыгранная роль не исчезает молча — помечена деградировавшей
    assert by_role["тактик"]["degraded"] is True
    assert out["degraded_roles"] == ["тактик"]
    assert out["diversity"] == "reduced" and out["complete"] is False
