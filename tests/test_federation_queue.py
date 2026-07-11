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
