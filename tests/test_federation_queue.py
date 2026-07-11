"""Субстрат очереди роль-тасков — domain-agnostic. SQLite single-writer, claim_token idempotency."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.queue import RoleTask, Claim, QueueBackend


def test_roletask_and_claim_shapes():
    t = RoleTask(session_id="s1", role="aurelius", advisor_dir="advisors/aurelius",
                 question="Q?", priority=0, max_attempts=3)
    assert t.session_id == "s1" and t.role == "aurelius" and t.max_attempts == 3
    c = Claim(task_id="t1", claim_token="tok", role="aurelius",
              advisor_dir="advisors/aurelius", question="Q?")
    assert c.task_id == "t1" and c.claim_token == "tok"


def test_queuebackend_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        QueueBackend()


import tempfile


def _mk(tmp_path):
    from federation.queue import SqliteBackend
    return SqliteBackend(str(tmp_path / "q.sqlite3"))


def test_enqueue_then_claim_returns_task(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    tid = q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    assert isinstance(tid, str) and tid
    c = q.claim("w1")
    assert c is not None and c.task_id == tid and c.role == "aurelius"
    assert c.claim_token
    assert c.question == "Q?"


def test_claim_empty_queue_returns_none(tmp_path):
    q = _mk(tmp_path)
    assert q.claim("w1") is None


def test_claim_filters_by_role(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    assert q.claim("w1", roles=["machiavelli"]) is None
    c = q.claim("w1", roles=["aurelius"])
    assert c is not None and c.role == "aurelius"


def test_status_counts_by_state(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    q.enqueue(RoleTask("s1", "machiavelli", "advisors/machiavelli", "Q?"))
    q.claim("w1")
    st = q.status("s1")
    assert st["pending"] == 1 and st["claimed"] == 1 and st["done"] == 0


def test_ack_with_valid_token_marks_done(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    r = q.ack(c.task_id, "w1", c.claim_token, {"argument": "хм"})
    assert r["ok"] is True
    assert q.status("s1")["done"] == 1


def test_ack_stale_token_rejected(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    r = q.ack(c.task_id, "w1", "не-тот-токен", {"argument": "мусор"})
    assert r.get("stale") is True and r.get("ok") is not True
    assert q.status("s1")["done"] == 0


def test_ack_wrong_worker_rejected(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    r = q.ack(c.task_id, "w2", c.claim_token, {"x": 1})
    assert r.get("stale") is True


def test_nack_requeues_until_retry_cap_then_dead(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?", max_attempts=2))
    c = q.claim("w1")
    assert q.nack(c.task_id, "w1", c.claim_token, "boom")["ok"] is True
    assert q.status("s1")["pending"] == 1
    c = q.claim("w1")
    r = q.nack(c.task_id, "w1", c.claim_token, "boom2")
    assert r.get("dead") is True
    assert q.status("s1")["dead"] == 1


def test_heartbeat_valid_token_ok_stale_rejected(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    assert q.heartbeat(c.task_id, "w1", c.claim_token)["ok"] is True
    assert q.heartbeat(c.task_id, "w1", "плохой-токен").get("stale") is True
