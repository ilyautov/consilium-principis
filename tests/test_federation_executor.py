"""Исполнитель: claim отдаёт СТРУКТУРНЫЙ бриф (не shell-строку — заимствование trust-boundary),
submit валидирует и кладёт сырьё через ack (маркеры НЕ ставит — сервер сверит на assemble)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.queue import SqliteBackend, RoleTask
from federation.executor import claim_brief, heartbeat_task


def _q(tmp_path):
    return SqliteBackend(str(tmp_path / "ex.sqlite3"))


def test_claim_brief_returns_structural_brief(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Как быть?"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    assert b["role"] == "aurelius"
    assert b["advisor_dir"] == "advisors/aurelius"
    assert b["question"] == "Как быть?"
    assert isinstance(b["task_id"], str) and isinstance(b["claim_token"], str)
    # бриф — данные, НЕ собранная команда: никаких shell-строк
    assert "$(" not in repr(b) and "`" not in repr(b)


def test_claim_brief_empty_when_none(tmp_path):
    q = _q(tmp_path)
    b = claim_brief(q, "w1", roles=None, timeout=0.2)
    assert b == {"empty": True}


def test_heartbeat_roundtrip(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    hb = heartbeat_task(q, b["task_id"], "w1", b["claim_token"])
    assert hb.get("ok") is True
    stale = heartbeat_task(q, b["task_id"], "w1", "wrong-token")
    assert stale.get("stale") is True
