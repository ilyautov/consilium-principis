# Tier-2 Federation — Part A: Queue Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить domain-agnostic субстрат очереди роль-тасков (`scripts/federation/queue.py` + `notify.py`): `QueueBackend` ABC + `SqliteBackend` с idempotent claim/ack (claim_token), retry-капом, sweep-reclaim, и notify+poll listen-циклом с блокирующим `claim`.

**Architecture:** SQLite-бэкенд (stdlib `sqlite3`, WAL, `BEGIN IMMEDIATE`, single-writer сериализация → нет гонки claim). Idempotency через per-claim `claim_token` (uuid4): ack/nack/heartbeat валидны только с текущим токеном → поздний ответ реклейменного таска отбрасывается. `claim(block=True, timeout=N)` внутри = sleep-poll + `Notifier.wait` (FIFO мгновенное пробуждение на POSIX, sleep-poll фолбэк), full-jitter backoff. Ноль совет-логики — чистый субстрат.

**Tech Stack:** Python 3 stdlib (`sqlite3`, `uuid`, `os`, `select`, `time`, `random`, `json`, `abc`), pytest, `multiprocessing` для кросс-процессных тестов.

**Offline CI (ВСЕГДА):** `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`. Игнорировать env-flaky `test_ssrf_check_passes_public_blocks_private`. Ветка `feat/tier2-federation`, без push/merge. `.consilium/` уже в `.gitignore`. Новый тест-файл сдвигает `docs/selfdoc/index.json` → `test_selfdoc_fresh` падает → `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`, коммить оба selfdoc-файла.

---

## File Structure

- `scripts/federation/__init__.py` — пакет (пустой; делает `federation` импортируемым как `from federation.queue import ...` при `sys.path` включающем `scripts/`).
- `scripts/federation/queue.py` — `RoleTask` (dataclass), `Claim` (dataclass), `QueueBackend` (ABC), `SqliteBackend`. Одна ответственность: durable-очередь с idempotent-семантикой.
- `scripts/federation/notify.py` — `Notifier` (ABC), `FifoNotifier`, `PollNotifier`, `make_notifier(dir)`. Одна ответственность: пробуждение воркера.
- `tests/test_federation_queue.py` — юнит + кросс-процессные тесты очереди.
- `tests/test_federation_notify.py` — тесты notify/listen.

NB: `scripts/` уже на `sys.path` в тестах через `sys.path.insert(0, os.path.join(HERE,"..","scripts"))`. Внутри-пакетные импорты пиши как `from federation.queue import ...`.

---

### Task 1: Пакет + `RoleTask`/`Claim` датаклассы + `QueueBackend` ABC

**Files:**
- Create: `scripts/federation/__init__.py`
- Create: `scripts/federation/queue.py`
- Test: `tests/test_federation_queue.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_federation_queue.py
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
        QueueBackend()          # ABC — прямое инстанцирование запрещено
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'federation'`

- [ ] **Step 3: Create `scripts/federation/__init__.py`**

```python
"""Tier-2 федерация — субстрат очереди (domain-agnostic) + координатор/исполнитель (Часть B)."""
```

- [ ] **Step 4: Write `scripts/federation/queue.py`**

```python
"""Субстрат очереди роль-тасков. SQLite single-writer сериализует claim'ы (гонки нет).
Idempotency: per-claim claim_token — ack/nack/heartbeat валидны только с текущим токеном,
поздний ответ реклейменного таска отбрасывается ({stale}). Domain-agnostic: ноль совет-логики."""
import abc
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add scripts/federation/__init__.py scripts/federation/queue.py tests/test_federation_queue.py
git commit -m "feat(federation): пакет + RoleTask/Claim/QueueBackend ABC"
```
(конец тела коммита — всегда две строки-трейлера этого репо:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UxyLokySN44W2qzEmWMrMK )

---

### Task 2: `SqliteBackend` — схема, enqueue, claim (BEGIN IMMEDIATE + claim_token), status

**Files:**
- Modify: `scripts/federation/queue.py`
- Test: `tests/test_federation_queue.py`

- [ ] **Step 1: Write the failing test** (добавить в конец файла)

```python
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
    assert c.claim_token                      # непустой токен на каждый claim
    assert c.question == "Q?"


def test_claim_empty_queue_returns_none(tmp_path):
    q = _mk(tmp_path)
    assert q.claim("w1") is None              # ничего в очереди → None (не блокируемся при block=False)


def test_claim_filters_by_role(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    assert q.claim("w1", roles=["machiavelli"]) is None       # нет тасков этой роли
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: FAIL with `ImportError: cannot import name 'SqliteBackend'`

- [ ] **Step 3: Add `SqliteBackend` to `scripts/federation/queue.py`** (после ABC; импорты вверху файла: добавь `import os, sqlite3, time, uuid, json`)

```python
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
            if c.total_changes == 0:            # проиграл гонку (другой процесс успел) → пусто
                c.execute("COMMIT")
                return None
            r = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            c.execute("COMMIT")
            return Claim(task_id=r["id"], claim_token=r["claim_token"], role=r["role"],
                         advisor_dir=r["advisor_dir"], question=r["question"])
        finally:
            c.close()

    def claim(self, worker_id, roles=None, block=False, timeout=0.0):
        # block-путь дорабатывается в Task 5 (notify). Здесь — одноразовый claim.
        return self._claim_once(worker_id, roles)

    def status(self, session_id):
        with self._conn() as c:
            rows = c.execute("SELECT status, COUNT(*) n FROM tasks WHERE session_id=? "
                             "GROUP BY status", (session_id,)).fetchall()
        out = {"pending": 0, "claimed": 0, "done": 0, "dead": 0}
        for r in rows:
            out[r["status"]] = r["n"]
        return out
```

Примечание: `_HAS_RETURNING` пока не используется в claim (используем портируемый SELECT→UPDATE в одной транзакции — работает на ЛЮБОЙ версии, single-writer гарантирует отсутствие гонки). Флаг оставлен для Task 3-теста фолбэка и как явная документация версии. Реализация claim НЕ зависит от RETURNING намеренно (проще + переносимо).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/queue.py tests/test_federation_queue.py
git commit -m "feat(federation): SqliteBackend схема+enqueue+claim(BEGIN IMMEDIATE,claim_token)+status"
```
(+ трейлеры репо)

---

### Task 3: Idempotent `ack`/`nack`/`heartbeat` (claim_token) + retry-кап → dead

**Files:**
- Modify: `scripts/federation/queue.py`
- Test: `tests/test_federation_queue.py`

- [ ] **Step 1: Write the failing test** (в конец файла)

```python
def test_ack_with_valid_token_marks_done(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    r = q.ack(c.task_id, "w1", c.claim_token, {"argument": "хм"})
    assert r["ok"] is True
    assert q.status("s1")["done"] == 1


def test_ack_stale_token_rejected(tmp_path):
    # реклейм-сценарий: поздний ответ старого воркера с протухшим токеном → отброшен
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    r = q.ack(c.task_id, "w1", "не-тот-токен", {"argument": "мусор"})
    assert r.get("stale") is True and r.get("ok") is not True
    assert q.status("s1")["done"] == 0         # result НЕ записан


def test_ack_wrong_worker_rejected(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    r = q.ack(c.task_id, "w2", c.claim_token, {"x": 1})   # чужой worker_id
    assert r.get("stale") is True


def test_nack_requeues_until_retry_cap_then_dead(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?", max_attempts=2))
    c = q.claim("w1")                           # attempts=1
    assert q.nack(c.task_id, "w1", c.claim_token, "boom")["ok"] is True
    assert q.status("s1")["pending"] == 1       # вернулся
    c = q.claim("w1")                           # attempts=2 == max → следующий nack убьёт
    r = q.nack(c.task_id, "w1", c.claim_token, "boom2")
    assert r.get("dead") is True
    assert q.status("s1")["dead"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: FAIL with `AttributeError: 'SqliteBackend' object has no attribute 'ack'`

- [ ] **Step 3: Add `ack`/`nack`/`heartbeat` to `SqliteBackend`**

```python
    def _guard(self, c, task_id, worker_id, claim_token):
        """Возвращает row если (claimed этим воркером с этим токеном), иначе None (stale)."""
        r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not r or r["status"] != "claimed" or r["claimed_by"] != worker_id \
                or r["claim_token"] != claim_token:
            return None
        return r

    def ack(self, task_id, worker_id, claim_token, result):
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if self._guard(c, task_id, worker_id, claim_token) is None:
                c.execute("COMMIT")
                return {"stale": True}
            c.execute("UPDATE tasks SET status='done', result_json=? WHERE id=?",
                      (json.dumps(result, ensure_ascii=False), task_id))
            c.execute("COMMIT")
        return {"ok": True}

    def nack(self, task_id, worker_id, claim_token, error):
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            r = self._guard(c, task_id, worker_id, claim_token)
            if r is None:
                c.execute("COMMIT")
                return {"stale": True}
            if r["attempts"] >= r["max_attempts"]:      # исчерпан retry → dead-letter
                c.execute("UPDATE tasks SET status='dead', error=? WHERE id=?", (error, task_id))
                c.execute("COMMIT")
                return {"dead": True}
            c.execute("UPDATE tasks SET status='pending', claimed_by=NULL, claim_token=NULL, "
                      "claimed_at=NULL, error=? WHERE id=?", (error, task_id))
            c.execute("COMMIT")
        return {"ok": True}

    def heartbeat(self, task_id, worker_id, claim_token):
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if self._guard(c, task_id, worker_id, claim_token) is None:
                c.execute("COMMIT")
                return {"stale": True}
            c.execute("UPDATE tasks SET claimed_at=? WHERE id=?", (time.time(), task_id))
            c.execute("COMMIT")
        return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: PASS (все ack/nack/heartbeat-тесты Task 3 зелёные; они не зависят от sweep — nack retry-кап тестится через claim→nack→claim→nack без реклейма). ABA-тест (требует sweep) — в Task 4.

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/queue.py tests/test_federation_queue.py
git commit -m "feat(federation): idempotent ack/nack/heartbeat (claim_token) + retry-кап→dead"
```
(+ трейлеры)

---

### Task 4: `sweep` — реклейм протухших claim (lease) + dead при исчерпании retry

**Files:**
- Modify: `scripts/federation/queue.py`
- Test: `tests/test_federation_queue.py`

- [ ] **Step 1: Write the failing test** (в конец файла)

```python
def test_sweep_reclaims_expired_claim(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    assert q.status("s1")["claimed"] == 1
    n = q.sweep(lease_seconds=0)                # lease=0 → любой claim протух немедленно
    assert n == 1
    assert q.status("s1")["pending"] == 1       # вернулся в pending
    # старый воркер теперь stale (токен обнулён)
    assert q.ack(c.task_id, "w1", c.claim_token, {"x": 1}).get("stale") is True


def test_sweep_kills_when_retry_exhausted(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?", max_attempts=1))
    q.claim("w1")                               # attempts=1 == max
    n = q.sweep(lease_seconds=0)
    assert n == 1
    assert q.status("s1")["dead"] == 1          # реклейм при исчерпанном retry → dead, не pending


def test_sweep_leaves_fresh_claims(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    q.claim("w1")
    assert q.sweep(lease_seconds=9999) == 0     # свежий claim не трогаем
    assert q.status("s1")["claimed"] == 1


def test_aba_old_token_stale_after_reclaim(tmp_path):
    # ABA: sweep реклеймит в pending, тот же воркер claim'ит снова (НОВЫЙ токен) → старый токен stale
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c1 = q.claim("w1")
    q.sweep(lease_seconds=0)                    # немедленный реклейм в pending
    c2 = q.claim("w1")                          # снова claim → НОВЫЙ токен
    assert c2.claim_token != c1.claim_token
    assert q.ack(c1.task_id, "w1", c1.claim_token, {"x": 1}).get("stale") is True   # старый stale
    assert q.ack(c2.task_id, "w1", c2.claim_token, {"x": 2})["ok"] is True          # новый ок
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: FAIL (`AttributeError: sweep`)

- [ ] **Step 3: Add `sweep` to `SqliteBackend`**

```python
    def sweep(self, lease_seconds):
        cutoff = time.time() - lease_seconds
        with self._conn() as c:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: PASS (все queue-тесты, включая Task 3 ABA/retry, теперь зелёные)

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/queue.py tests/test_federation_queue.py
git commit -m "feat(federation): sweep — реклейм протухших claim по lease + dead при исчерпании retry"
```
(+ трейлеры)

---

### Task 5: Кросс-процессная гонка claim (единственность) + RETURNING-фолбэк документирован

**Files:**
- Test: `tests/test_federation_queue.py`

- [ ] **Step 1: Write the failing test** (в конец файла) — реальные ПРОЦЕССЫ, не потоки

```python
def _claim_worker(db_path, worker_id, out_q):
    # запускается в ОТДЕЛЬНОМ процессе (spawn) — реальный file-lock, не GIL
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    from federation.queue import SqliteBackend
    q = SqliteBackend(db_path)
    got = []
    for _ in range(50):
        c = q.claim(worker_id)
        if c:
            got.append(c.task_id)
    out_q.put(got)


def test_cross_process_claim_each_task_once(tmp_path):
    import multiprocessing as mp
    from federation.queue import RoleTask
    db = str(tmp_path / "race.sqlite3")
    q = SqliteBackend(db) if False else __import__("federation.queue", fromlist=["SqliteBackend"]).SqliteBackend(db)
    N = 30
    for i in range(N):
        q.enqueue(RoleTask("s1", "r", "advisors/r", "Q%d" % i))
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    procs = [ctx.Process(target=_claim_worker, args=(db, "w%d" % k, out)) for k in range(4)]
    for p in procs: p.start()
    collected = []
    for _ in procs:
        collected += out.get(timeout=30)
    for p in procs: p.join(timeout=30)
    # каждый таск заклеймлен РОВНО один раз (single-writer сериализация)
    assert len(collected) == N
    assert len(set(collected)) == N


def test_returning_version_flag_present():
    # фолбэк-путь: реализация claim НЕ зависит от RETURNING (переносима на <3.35);
    # флаг существует как явная документация версии
    from federation.queue import _HAS_RETURNING
    assert isinstance(_HAS_RETURNING, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: если `SqliteBackend` не импортирован на уровне модуля в тесте — поправь верх файла: `from federation.queue import RoleTask, Claim, QueueBackend, SqliteBackend`. Тогда FAIL превращается в проверку самой гонки. (Изначально FAIL из-за `NameError: SqliteBackend` в helper — импорт внутри `_claim_worker` его чинит для дочернего процесса.)

- [ ] **Step 3: Fix module-level import in test file** — заменить верхний импорт на:

```python
from federation.queue import RoleTask, Claim, QueueBackend, SqliteBackend
```

и упростить строку в `test_cross_process_claim_each_task_once`:

```python
    db = str(tmp_path / "race.sqlite3")
    q = SqliteBackend(db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: PASS (гонка: 30 тасков, 4 процесса, каждый таск ровно раз)

- [ ] **Step 5: Commit**

```bash
git add tests/test_federation_queue.py
git commit -m "test(federation): кросс-процессная гонка claim (single-writer единственность) + версия-флаг"
```
(+ трейлеры)

---

### Task 6: `Notifier` — FifoNotifier (POSIX) + PollNotifier (фолбэк) + `make_notifier`

**Files:**
- Create: `scripts/federation/notify.py`
- Test: `tests/test_federation_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_federation_notify.py
"""Notify-слой: FIFO мгновенное пробуждение (POSIX) + sleep-poll фолбэк. poll — источник истины."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.notify import PollNotifier, make_notifier


def test_poll_notifier_wait_times_out():
    n = PollNotifier()
    t0 = time.time()
    n.wait(0.2)
    assert time.time() - t0 >= 0.18            # действительно спал ~timeout
    n.notify()                                  # no-op, не падает


def test_make_notifier_returns_usable(tmp_path):
    n = make_notifier(str(tmp_path))
    n.notify()                                  # не падает независимо от платформы
    t0 = time.time()
    n.wait(0.1)                                 # завершается (по звонку или таймауту)
    assert time.time() - t0 < 2.0


def test_fifo_notifier_wakes_fast_when_available(tmp_path):
    # на POSIX make_notifier даёт FIFO — notify() будит wait() быстрее полного таймаута
    if not hasattr(os, "mkfifo"):
        import pytest; pytest.skip("нет mkfifo (не-POSIX) — FIFO-путь недоступен")
    from federation.notify import FifoNotifier
    n = FifoNotifier(str(tmp_path))
    import threading
    def ring():
        time.sleep(0.1); n.notify()
    threading.Thread(target=ring, daemon=True).start()
    t0 = time.time()
    n.wait(5.0)                                 # должен проснуться ~0.1с, НЕ ждать 5с
    dt = time.time() - t0
    assert dt < 1.0, "FIFO не разбудил быстро: %.2f" % dt
    n.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_notify.py -q`
Expected: FAIL (`ModuleNotFoundError` / `ImportError`)

- [ ] **Step 3: Write `scripts/federation/notify.py`**

```python
"""Пробуждение воркера. poll — источник истины (потолок гарантирует доставку), notify — акселерант
латентности, надёжным быть НЕ обязан (потерянный звонок → poll подберёт)."""
import os
import time
import select


class Notifier:
    def notify(self): ...
    def wait(self, timeout): ...
    def close(self): ...


class PollNotifier(Notifier):
    """Фолбэк (Windows / нет mkfifo): wait = sleep. Пробуждения нет — только таймаут-poll."""
    def notify(self):
        pass

    def wait(self, timeout):
        if timeout > 0:
            time.sleep(timeout)

    def close(self):
        pass


class FifoNotifier(Notifier):
    """POSIX: FIFO. wait блокируется на select(read_fd); notify пишет байт → мгновенное пробуждение.
    Потеря звонка (нет читателя / EAGAIN) допустима — poll-потолок подберёт таск."""
    def __init__(self, dir_path):
        os.makedirs(dir_path, exist_ok=True)
        self.path = os.path.join(dir_path, "federation.wake")
        if not os.path.exists(self.path):
            os.mkfifo(self.path)
        # держим свой RW-дескриптор на чтение (O_RDWR не блокируется на open даже без писателей)
        self._rfd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)

    def notify(self):
        try:
            wfd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(wfd, b"\x01")
            finally:
                os.close(wfd)
        except OSError:
            pass                                # нет читателя/полный буфер → потеря ок

    def wait(self, timeout):
        try:
            r, _, _ = select.select([self._rfd], [], [], timeout)
        except (OSError, ValueError):
            time.sleep(min(timeout, 0.5)); return
        if r:
            try:
                os.read(self._rfd, 4096)        # осушить, чтобы не будило повторно
            except OSError:
                pass

    def close(self):
        try:
            os.close(self._rfd)
        except OSError:
            pass


def make_notifier(dir_path):
    """FIFO на POSIX, иначе PollNotifier. Fail-safe: любая ошибка создания FIFO → PollNotifier."""
    if hasattr(os, "mkfifo"):
        try:
            return FifoNotifier(dir_path)
        except OSError:
            pass
    return PollNotifier()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_notify.py -q`
Expected: PASS (3 passed на POSIX; на не-POSIX FIFO-тест skip)

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/notify.py tests/test_federation_notify.py
git commit -m "feat(federation): Notifier — FifoNotifier(POSIX мгновенно) + PollNotifier(фолбэк)"
```
(+ трейлеры)

---

### Task 7: Блокирующий `claim(block=True, timeout)` — notify+poll listen-цикл с backoff

**Files:**
- Modify: `scripts/federation/queue.py`
- Test: `tests/test_federation_notify.py`

- [ ] **Step 1: Write the failing test** (в конец `test_federation_notify.py`)

```python
from federation.queue import SqliteBackend, RoleTask


def _mkq(tmp_path):
    return SqliteBackend(str(tmp_path / "q.sqlite3"))


def test_block_returns_none_on_timeout_when_empty(tmp_path):
    q = _mkq(tmp_path)
    t0 = time.time()
    c = q.claim("w1", block=True, timeout=0.3)
    assert c is None and time.time() - t0 >= 0.25      # блокировался до таймаута


def test_block_returns_task_when_present(tmp_path):
    q = _mkq(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1", block=True, timeout=2.0)
    assert c is not None and c.role == "aurelius"      # взял сразу, не ждал полный таймаут


def test_block_wakes_on_late_enqueue_before_ceiling(tmp_path):
    # таск появляется через 0.2с; block должен вернуть его СИЛЬНО раньше 5с потолка
    import threading
    q = _mkq(tmp_path)
    def add():
        time.sleep(0.2); q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    threading.Thread(target=add, daemon=True).start()
    t0 = time.time()
    c = q.claim("w1", block=True, timeout=5.0)
    dt = time.time() - t0
    assert c is not None and dt < 3.0                  # poll-бэкстоп (и notify если тот же процесс) подобрал


def test_cross_process_block_claim_single_owner(tmp_path):
    # N процессов блокирующе-claim'ят; каждый таск ровно раз
    import multiprocessing as mp
    q = _mkq(tmp_path)
    N = 12
    for i in range(N):
        q.enqueue(RoleTask("s1", "r", "advisors/r", "Q%d" % i))
    db = q.db_path
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    def target(): pass
    procs = [ctx.Process(target=_block_worker, args=(db, "w%d" % k, N, out)) for k in range(3)]
    for p in procs: p.start()
    got = []
    for _ in procs: got += out.get(timeout=30)
    for p in procs: p.join(timeout=30)
    assert sorted(got) == sorted(set(got)) and len(set(got)) == N


def _block_worker(db_path, worker_id, target_n, out_q):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    from federation.queue import SqliteBackend
    q = SqliteBackend(db_path)
    got = []
    while True:
        c = q.claim(worker_id, block=True, timeout=0.5)
        if c is None:
            break                               # очередь исчерпана (таймаут без таска)
        got.append(c.task_id)
    out_q.put(got)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_notify.py -q`
Expected: FAIL — `test_block_returns_none_on_timeout` виснет/возвращает сразу (block пока = одноразовый claim из Task 2).

- [ ] **Step 3: Rework `claim` in `scripts/federation/queue.py`** (импорты вверху: добавь `import random`; создаём notifier лениво)

Заменить метод `claim` на:

```python
    def _notifier(self):
        if getattr(self, "_notif", None) is None:
            from federation.notify import make_notifier
            self._notif = make_notifier(os.path.dirname(self.db_path) or ".")
        return self._notif

    def claim(self, worker_id, roles=None, block=False, timeout=0.0):
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
```

И в `enqueue` добавь звонок после успешной вставки (перед `return tid`):

```python
        try:
            self._notifier().notify()
        except Exception:
            pass                                    # notify не критичен (poll — истина)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_notify.py tests/test_federation_queue.py -q`
Expected: PASS (все федерация-тесты; block по таймауту, по появлению, по позднему enqueue, кросс-процессно единственность)

- [ ] **Step 5: Regen selfdoc if needed + Commit**

Если `test_selfdoc_fresh` упал (новые тест-файлы): `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`, затем прогон всего сьюта.

```bash
git add scripts/federation/queue.py tests/test_federation_notify.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "feat(federation): блокирующий claim(block,timeout) — notify+poll listen с full-jitter backoff"
```
(+ трейлеры)

- [ ] **Step 6: Full offline suite green**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: весь сьют зелёный (+ федерация). Игнор env-flaky SSRF.

---

## Self-Review (план против спеки, Часть A)

- **Покрытие:** QueueBackend ABC (T1), SqliteBackend схема/enqueue/claim/status (T2), idempotent ack/nack/heartbeat + retry-кап (T3), sweep-reclaim + dead (T4), кросс-процессная гонка + версия-флаг (T5), Notifier FIFO/Poll (T6), блокирующий claim notify+poll backoff (T7). Все пункты Части A спеки закрыты.
- **claim_token idempotency (улучш. 3):** T3 (stale/wrong-worker/ABA), закрыт `_guard`.
- **retry-кап (улучш. 7):** T3 nack + T4 sweep → dead.
- **кросс-процесс (улучш. 6):** T5 + T7 `multiprocessing spawn`, не потоки.
- **notify+poll:** T6 (Notifier) + T7 (listen-цикл, poll-бэкстоп, backoff).
- **Типы согласованы:** `Claim(task_id, claim_token, role, advisor_dir, question)`; `ack/nack/heartbeat(task_id, worker_id, claim_token, ...)`; `sweep(lease_seconds)`; `status(session_id)` — единообразны во всех задачах.
- **Плейсхолдеров нет** — весь код приведён.
- **Границы:** ноль совет-логики (координатор/исполнитель/верность/дивергенция — Часть B, отдельный план).
