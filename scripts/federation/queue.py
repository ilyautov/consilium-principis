"""Субстрат очереди роль-тасков. SQLite single-writer сериализует claim'ы (гонки нет).
Idempotency: per-claim claim_token — ack/nack/heartbeat валидны только с текущим токеном,
поздний ответ реклейменного таска отбрасывается ({stale}). Domain-agnostic: ноль совет-логики."""
import abc
import os
import sqlite3
import time
import uuid
import json
from dataclasses import dataclass


@dataclass
class RoleTask:
    session_id: str
    role: str
    advisor_dir: str
    question: str
    priority: int = 0
    max_attempts: int = 3


@dataclass
class Claim:
    task_id: str
    claim_token: str
    role: str
    advisor_dir: str
    question: str


class QueueBackend(abc.ABC):
    """Шов: SqliteBackend сейчас; RedisBackend/HttpBackend/PostgresBackend (team/corp) позже —
    тот же интерфейс, block=True разблокируется нативным BLPOP/subscribe без правок вызывающих."""

    @abc.abstractmethod
    def enqueue(self, task: RoleTask) -> str: ...

    @abc.abstractmethod
    def claim(self, worker_id: str, roles=None, block: bool = False, timeout: float = 0.0): ...

    @abc.abstractmethod
    def ack(self, task_id: str, worker_id: str, claim_token: str, result: dict) -> dict: ...

    @abc.abstractmethod
    def nack(self, task_id: str, worker_id: str, claim_token: str, error: str) -> dict: ...

    @abc.abstractmethod
    def heartbeat(self, task_id: str, worker_id: str, claim_token: str) -> dict: ...

    @abc.abstractmethod
    def sweep(self, lease_seconds: float) -> int: ...

    @abc.abstractmethod
    def status(self, session_id: str) -> dict: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL,
    advisor_dir TEXT NOT NULL, question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    claimed_by TEXT, claim_token TEXT, claimed_at REAL,
    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
    result_json TEXT, error TEXT, created_at REAL NOT NULL, priority INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pending ON tasks(status, priority, created_at);
"""
_HAS_RETURNING = sqlite3.sqlite_version_info >= (3, 35, 0)


class SqliteBackend(QueueBackend):
    def __init__(self, db_path):
        self.db_path = db_path
        d = os.path.dirname(db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def enqueue(self, task):
        tid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("INSERT INTO tasks(id,session_id,role,advisor_dir,question,status,"
                      "attempts,max_attempts,created_at,priority) VALUES(?,?,?,?,?,'pending',0,?,?,?)",
                      (tid, task.session_id, task.role, task.advisor_dir, task.question,
                       task.max_attempts, time.time(), task.priority))
        return tid

    def _claim_once(self, worker_id, roles):
        token = uuid.uuid4().hex
        now = time.time()
        role_ok = "1=1" if not roles else "role IN (%s)" % ",".join("?" * len(roles))
        params_sel = list(roles) if roles else []
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT id FROM tasks WHERE status='pending' AND %s "
                "ORDER BY priority, created_at LIMIT 1" % role_ok, params_sel).fetchone()
            if not row:
                c.execute("COMMIT")
                return None
            tid = row["id"]
            c.execute("UPDATE tasks SET status='claimed', claimed_by=?, claim_token=?, "
                      "claimed_at=?, attempts=attempts+1 WHERE id=? AND status='pending'",
                      (worker_id, token, now, tid))
            if c.total_changes == 0:
                c.execute("COMMIT")
                return None
            r = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            c.execute("COMMIT")
            return Claim(task_id=r["id"], claim_token=r["claim_token"], role=r["role"],
                         advisor_dir=r["advisor_dir"], question=r["question"])
        finally:
            c.close()

    def claim(self, worker_id, roles=None, block=False, timeout=0.0):
        return self._claim_once(worker_id, roles)

    def ack(self, task_id, worker_id, claim_token, result):
        raise NotImplementedError  # Task 3

    def nack(self, task_id, worker_id, claim_token, error):
        raise NotImplementedError  # Task 3

    def heartbeat(self, task_id, worker_id, claim_token):
        raise NotImplementedError  # Task 4

    def sweep(self, lease_seconds):
        raise NotImplementedError  # Task 4

    def status(self, session_id):
        with self._conn() as c:
            rows = c.execute("SELECT status, COUNT(*) n FROM tasks WHERE session_id=? "
                             "GROUP BY status", (session_id,)).fetchall()
        out = {"pending": 0, "claimed": 0, "done": 0, "dead": 0}
        for r in rows:
            out[r["status"]] = r["n"]
        return out
