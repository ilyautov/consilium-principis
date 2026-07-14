"""Субстрат очереди роль-тасков. SQLite single-writer сериализует claim'ы (гонки нет).
Idempotency: per-claim claim_token — ack/nack/heartbeat валидны только с текущим токеном,
поздний ответ реклейменного таска отбрасывается ({stale}). Domain-agnostic: ноль совет-логики."""
import abc
import contextlib
import os
import random
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
    def claim(self, worker_id: str, roles=None, block: bool = False, timeout: float = 0.0,
              lease_seconds=None): ...

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

    @abc.abstractmethod
    def results(self, session_id: str, status="done") -> list: ...


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

# Аренда роли по умолчанию. Щедрая намеренно: советника играет МОДЕЛЬ, она думает минуты, и
# не всякий воркер зовёт heartbeat. Слишком короткий lease увёл бы роль из-под живого воркера —
# его submit потом отлетел бы как stale (порчи нет, claim_token защищает), но работа задвоилась бы.
DEFAULT_LEASE_S = 300.0


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
        with contextlib.closing(self._conn()) as c:
            with c:
                c.execute("INSERT INTO tasks(id,session_id,role,advisor_dir,question,status,"
                          "attempts,max_attempts,created_at,priority) VALUES(?,?,?,?,?,'pending',0,?,?,?)",
                          (tid, task.session_id, task.role, task.advisor_dir, task.question,
                           task.max_attempts, time.time(), task.priority))
        try:
            self._notifier().notify()
        except Exception:
            pass                                    # notify не критичен (poll — истина)
        return tid

    def _claim_once(self, worker_id, roles):
        if roles is not None and len(roles) == 0:
            return None                          # пустой список ролей = нечего клеймить (не «любую»)
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

    def _notifier(self):
        if getattr(self, "_notif", None) is None:
            from federation.notify import make_notifier
            self._notif = make_notifier(os.path.dirname(self.db_path) or ".")
        return self._notif

    # NB: под экстрим-контеншеном (>busy_timeout=5s) sqlite может бросить OperationalError
    # "database is locked" — намеренно НЕ глотаем (fail-loud): таск самоисцелится через sweep
    # по истечении lease, дубля/порчи нет. Ретрай-обёртку не добавляем (лишняя сложность).
    def claim(self, worker_id, roles=None, block=False, timeout=0.0,
              lease_seconds=DEFAULT_LEASE_S):
        # Само-исцеление В ТОЧКЕ НУЖДЫ: воркер, пришедший за работой, сперва возвращает в
        # очередь роли умерших воркеров. До этого sweep был реализован, но его не звал НИКТО
        # (ни поток, ни демон, ни тул) → упавший воркер держал роль в 'claimed' вечно.
        # Вскрыто живым догфудом 2026-07-14; для автономного воркер-цикла это несущее —
        # рядом нет человека, чтобы заметить залипание.
        #
        # Зовём ОДИН раз на входе, НЕ в backoff-цикле ниже: sweep — это BEGIN IMMEDIATE-запись,
        # а цикл крутится каждые ~0.5с → был бы write-шторм по single-writer.
        # Цена: роль, протухшая ПОКА воркер уже блокирован, будет подобрана не этим циклом, а
        # следующим вызовом claim. Реальный воркер-цикл перевыпускает claim (клиенты режут
        # tool-call по таймауту), так что на практике sweep случается регулярно.
        # lease_seconds=None отключает авто-sweep (для тестов/ручного контроля).
        if lease_seconds is not None:
            self.sweep(lease_seconds)
        c = self._claim_once(worker_id, roles)
        if c is not None or not block:
            return c
        deadline = time.time() + timeout
        base, cap, n = 0.05, 0.5, 0                 # full-jitter backoff (кэп 0.5с в MVP)
        notif = self._notifier()
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return None
            backoff = min(cap, base * (2 ** n))
            notif.wait(min(remaining, random.uniform(0, backoff)))   # notify будит раньше; poll-потолок
            n += 1
            c = self._claim_once(worker_id, roles)
            if c is not None:
                n = 0                                # активность → сброс backoff
                return c

    def _guard(self, c, task_id, worker_id, claim_token):
        """Возвращает row если (claimed этим воркером с этим токеном), иначе None (stale)."""
        r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not r or r["status"] != "claimed" or r["claimed_by"] != worker_id \
                or r["claim_token"] != claim_token:
            return None
        return r

    def ack(self, task_id, worker_id, claim_token, result):
        with contextlib.closing(self._conn()) as c:
            with c:
                c.execute("BEGIN IMMEDIATE")
                if self._guard(c, task_id, worker_id, claim_token) is None:
                    c.execute("COMMIT")
                    return {"stale": True}
                c.execute("UPDATE tasks SET status='done', result_json=? WHERE id=?",
                          (json.dumps(result, ensure_ascii=False), task_id))
                c.execute("COMMIT")
        return {"ok": True}

    def nack(self, task_id, worker_id, claim_token, error):
        with contextlib.closing(self._conn()) as c:
            with c:
                c.execute("BEGIN IMMEDIATE")
                r = self._guard(c, task_id, worker_id, claim_token)
                if r is None:
                    c.execute("COMMIT")
                    return {"stale": True}
                if r["attempts"] >= r["max_attempts"]:
                    c.execute("UPDATE tasks SET status='dead', error=? WHERE id=?", (error, task_id))
                    c.execute("COMMIT")
                    return {"dead": True}
                c.execute("UPDATE tasks SET status='pending', claimed_by=NULL, claim_token=NULL, "
                          "claimed_at=NULL, error=? WHERE id=?", (error, task_id))
                c.execute("COMMIT")
        return {"ok": True}

    def heartbeat(self, task_id, worker_id, claim_token):
        with contextlib.closing(self._conn()) as c:
            with c:
                c.execute("BEGIN IMMEDIATE")
                if self._guard(c, task_id, worker_id, claim_token) is None:
                    c.execute("COMMIT")
                    return {"stale": True}
                c.execute("UPDATE tasks SET claimed_at=? WHERE id=?", (time.time(), task_id))
                c.execute("COMMIT")
        return {"ok": True}

    def sweep(self, lease_seconds):
        cutoff = time.time() - lease_seconds
        with contextlib.closing(self._conn()) as c:
            with c:
                c.execute("BEGIN IMMEDIATE")
                rows = c.execute("SELECT id, attempts, max_attempts FROM tasks "
                                 "WHERE status='claimed' AND claimed_at < ?", (cutoff,)).fetchall()
                n = 0
                for r in rows:
                    if r["attempts"] >= r["max_attempts"]:
                        c.execute("UPDATE tasks SET status='dead', error='lease-expired,retry-exhausted' "
                                  "WHERE id=?", (r["id"],))
                    else:
                        c.execute("UPDATE tasks SET status='pending', claimed_by=NULL, "
                                  "claim_token=NULL, claimed_at=NULL WHERE id=?", (r["id"],))
                    n += 1
                c.execute("COMMIT")
        return n

    def status(self, session_id):
        with contextlib.closing(self._conn()) as c:
            with c:
                rows = c.execute("SELECT status, COUNT(*) n FROM tasks WHERE session_id=? "
                                 "GROUP BY status", (session_id,)).fetchall()
        out = {"pending": 0, "claimed": 0, "done": 0, "dead": 0}
        for r in rows:
            out[r["status"]] = r["n"]
        return out

    def results(self, session_id, status="done"):
        """Строки тасков сессии (result распарсен из json). status=None → все состояния.
        role/advisor_dir/question берутся из строки таска (их писал enqueuer — доверенно)."""
        import contextlib
        with contextlib.closing(self._conn()) as c:
            if status is None:
                cur = c.execute(
                    "SELECT id, role, advisor_dir, question, status, claimed_by, result_json "
                    "FROM tasks WHERE session_id=? ORDER BY created_at", (session_id,))
            else:
                cur = c.execute(
                    "SELECT id, role, advisor_dir, question, status, claimed_by, result_json "
                    "FROM tasks WHERE session_id=? AND status=? ORDER BY created_at",
                    (session_id, status))
            out = []
            for row in cur.fetchall():
                rj = row["result_json"]
                out.append({
                    "task_id": row["id"], "role": row["role"],
                    "advisor_dir": row["advisor_dir"], "question": row["question"],
                    "status": row["status"], "worker_id": row["claimed_by"],
                    "result": json.loads(rj) if rj else None,
                })
            return out

    def close(self):
        n = getattr(self, "_notif", None)
        if n is not None:
            try:
                n.close()
            finally:
                self._notif = None
