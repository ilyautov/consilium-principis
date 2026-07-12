"""Координатор: open кладёт реплики роль-тасков в очередь; poll читает статус-счётчики."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.queue import SqliteBackend, RoleTask
from federation.coordinator import open_session, poll_session


def _q(tmp_path):
    return SqliteBackend(str(tmp_path / "co.sqlite3"))


def test_open_enqueues_replicas_per_role(tmp_path):
    q = _q(tmp_path)
    plan = [{"role": "aurelius", "advisor_dir": "advisors/aurelius", "question": "Q1", "replicas": 3},
            {"role": "machiavelli", "advisor_dir": "advisors/machiavelli", "question": "Q1"}]
    r = open_session(q, "s1", plan, replicas_default=2)
    assert r["session_id"] == "s1"
    assert r["enqueued"] == 3 + 2                # aurelius×3 + machiavelli×2(дефолт)
    st = q.status("s1")
    assert st["pending"] == 5


def test_poll_returns_status_counts(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "r", "advisor_dir": "advisors/r", "question": "Q"}],
                 replicas_default=2)
    q.claim("w1")
    p = poll_session(q, "s1")
    assert p["pending"] == 1 and p["claimed"] == 1 and p["done"] == 0
