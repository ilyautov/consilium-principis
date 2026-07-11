# Tier-2 Federation — Part B (Council on Substrate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the council-federation layer on top of the Part-A queue substrate: a coordinator that fans out role-replica tasks and assembles candidates (preserving divergence, centralizing fidelity), an executor surface workers use to claim/submit/heartbeat, a rule-based best-of-N judge, MCP tools, and operator docs.

**Architecture:** Domain logic lives in `scripts/federation/{coordinator,executor,judge}.py` on top of Part-A's `queue.py`/`notify.py`. Workers (separately-launched Claude Code sessions) generate raw candidates on their OWN model; OUR server verifies every quote against the role's corpus at assemble time using the coordinator-written (trusted) `advisor_dir` — the worker never self-certifies a marker. Fidelity verification is injected as `verify_fn` to avoid a circular import with `mcp_server._fidelity_check`. MCP handlers wire a lazy `SqliteBackend` at `.consilium/federation.sqlite3` (gitignored).

**Tech Stack:** Python stdlib only (sqlite3, json, re, os, uuid). No new deps. Offline TDD.

**Offline test command (ALWAYS use this — never bare `pytest`):**
```
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```
The env-flaky `test_ssrf_check_passes_public_blocks_private` shows as `1 skipped` — that is expected, ignore it.

**Commit trailers — append to EVERY commit body:**
```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UxyLokySN44W2qzEmWMrMK
```

**Substrate API already built (Part A — do NOT re-implement):**
- `from federation.queue import RoleTask, Claim, QueueBackend, SqliteBackend`
- `RoleTask(session_id, role, advisor_dir, question, priority=0, max_attempts=3)`
- `Claim(task_id, claim_token, role, advisor_dir, question)`
- `SqliteBackend(db_path)` → `.enqueue(task)->id`, `.claim(worker_id, roles=None, block=False, timeout=0.0)->Claim|None`, `.ack(task_id, worker_id, claim_token, result:dict)->dict`, `.nack(...)`, `.heartbeat(...)`, `.sweep(lease_seconds)`, `.status(session_id)->{pending,claimed,done,dead}`, `.close()`.
- `ack` returns `{"ok": True}` on success or `{"stale": True}` when the claim_token/worker mismatches.
- The task row stores `advisor_dir` written by the enqueuer (trusted); the worker cannot alter it.

**File structure (Part B):**
- `scripts/federation/judge.py` — pure rubric functions (score, divergence, verdict). No I/O.
- `scripts/federation/executor.py` — worker-facing: `claim_brief`, `submit_candidate` (validation), `heartbeat_task`. Thin over the backend.
- `scripts/federation/coordinator.py` — `open_session`, `poll_session`, `assemble` (centralized fidelity via injected `verify_fn`, divergence, degrade).
- `scripts/federation/queue.py` — MODIFY: add read method `results(session_id, status="done")`.
- `scripts/mcp_server.py` — MODIFY: 6 handlers + TOOLS entries + `_fed_backend()` singleton + INSTRUCTIONS worker-loop block.
- `docs/FEDERATION.md` — operator doc (personal/attended/single-machine).
- Tests: `tests/test_federation_judge.py`, `tests/test_federation_executor.py`, `tests/test_federation_coordinator.py`, extend `tests/test_federation_queue.py`, `tests/test_mcp_server.py` (or a new `tests/test_federation_mcp.py`), extend `tests/test_no_dark_tools.py`.

**Shared shapes (consistent across all tasks):**
- Worker candidate (input to submit): `{"argument": str, "quotes": [{"text": str}, ...]}`. `worker_model` passed as a separate arg.
- Stored result (written by `ack`): `{"argument": str, "quotes": [{"text": str}, ...], "worker_model": str}`.
- Verified candidate (assemble output): `{"argument": str, "worker_model": str, "quotes": [{"text": str, "status": "🔵|🟢|🟡", "source": str}, ...]}`.
- `divergence`: `{"score": float, "level": "low"|"high", "flagged": bool}` (threshold 0.5; score = 1 − mean pairwise Jaccard similarity of argument token-sets).
- Role result: `{"role", "advisor_dir", "representative", "replicas":[...], "divergence":{...}, "worker_models":[...], "verdict": "PASS"|"FIX"|"ESCALATE"}`.
- Degraded role result: `{"role", "advisor_dir", "degraded": True, "mode": "host_single_brain", "diversity": "reduced", "verdict": "ESCALATE", "representative": None, "replicas": []}`.
- Validation limits: `MAX_ARGUMENT = 8000`, `MAX_QUOTES = 30`, `MAX_QUOTE = 2000`. Control chars = any `ord(c) < 0x20` except `\n \t \r`.

---

### Task 1: Backend read API — `results(session_id, status="done")`

**Files:**
- Modify: `scripts/federation/queue.py` (add abstract method to `QueueBackend`, concrete to `SqliteBackend`)
- Test: `tests/test_federation_queue.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_federation_queue.py`)

```python
def test_results_returns_done_with_parsed_result(tmp_path):
    q = SqliteBackend(str(tmp_path / "res.sqlite3"))
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    q.ack(c.task_id, "w1", c.claim_token, {"argument": "A", "quotes": [{"text": "t"}]})
    rows = q.results("s1")                       # дефолт status="done"
    assert len(rows) == 1
    r = rows[0]
    assert r["role"] == "aurelius"
    assert r["advisor_dir"] == "advisors/aurelius"   # доверенный dir из строки таска
    assert r["question"] == "Q?"
    assert r["status"] == "done"
    assert r["result"] == {"argument": "A", "quotes": [{"text": "t"}]}  # распарсенный json


def test_results_status_none_returns_all_states(tmp_path):
    q = SqliteBackend(str(tmp_path / "res2.sqlite3"))
    q.enqueue(RoleTask("s1", "r1", "advisors/r1", "Q1"))
    q.enqueue(RoleTask("s1", "r2", "advisors/r2", "Q2"))
    q.claim("w1")                                # один pending→claimed, второй pending
    rows = q.results("s1", status=None)          # все состояния
    assert len(rows) == 2
    assert {r["role"] for r in rows} == {"r1", "r2"}


def test_results_empty_session_is_empty(tmp_path):
    q = SqliteBackend(str(tmp_path / "res3.sqlite3"))
    assert q.results("nope") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: FAIL (`AttributeError: 'SqliteBackend' object has no attribute 'results'`).

- [ ] **Step 3: Implement**

In `scripts/federation/queue.py`, add to `QueueBackend` (after `status`):
```python
    @abc.abstractmethod
    def results(self, session_id: str, status="done") -> list: ...
```
Add to `SqliteBackend` (after `status`, before `close`):
```python
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
```
(`json` and `contextlib` are already imported at module top from Part A; if not, add them.)

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_queue.py -q`
Expected: PASS (all federation queue tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/queue.py tests/test_federation_queue.py
git commit -m "feat(federation): backend read-API results(session_id,status) — распарсенные результаты по сессии"
```
(with trailers)

---

### Task 2: Judge — `score_candidate`, `divergence`, `verdict` (pure, rule-based)

**Files:**
- Create: `scripts/federation/judge.py`
- Test: `tests/test_federation_judge.py`

- [ ] **Step 1: Write the failing test**

```python
"""Судья: rule-based рубрика (MVP). score — репрезентант; divergence — сохранение разнообразия;
verdict — PASS/FIX/ESCALATE (именование заимствовано из advisor-orchestrator-worker)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.judge import score_candidate, divergence, verdict


def _cand(arg, statuses):
    return {"argument": arg, "worker_model": "m",
            "quotes": [{"text": "t%d" % i, "status": s, "source": "src"} for i, s in enumerate(statuses)]}


def test_score_rewards_blue_over_green_over_none():
    assert score_candidate(_cand("a", ["🔵"])) > score_candidate(_cand("a", ["🟢"]))
    assert score_candidate(_cand("a", ["🟢"])) > score_candidate(_cand("a", ["🟡"]))
    assert score_candidate(_cand("a", [])) < score_candidate(_cand("a", ["🔵"]))


def test_divergence_low_when_arguments_agree():
    cands = [_cand("ship the mvp fast now", []), _cand("ship the mvp fast now", []),
             _cand("ship the mvp fast", [])]
    d = divergence(cands)
    assert d["level"] == "low" and d["flagged"] is False


def test_divergence_high_when_arguments_diverge():
    cands = [_cand("ship the mvp immediately today", []),
             _cand("wait gather more evidence first", []),
             _cand("abandon the project entirely instead", [])]
    d = divergence(cands)
    assert d["level"] == "high" and d["flagged"] is True and d["score"] >= 0.5


def test_divergence_single_candidate_is_low():
    d = divergence([_cand("solo", [])])
    assert d["level"] == "low" and d["flagged"] is False


def test_verdict_pass_fix_escalate():
    assert verdict(_cand("a", ["🔵"])) == "PASS"          # есть заземление 🔵
    assert verdict(_cand("a", ["🟡"])) == "FIX"           # аргумент есть, грунта нет
    assert verdict(_cand("", [])) == "FIX"                # пустой аргумент, но кандидат есть → FIX
    assert verdict(None) == "ESCALATE"                    # кандидата нет вовсе
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_judge.py -q`
Expected: FAIL (`ModuleNotFoundError: federation.judge`).

- [ ] **Step 3: Implement `scripts/federation/judge.py`**

```python
"""Rule-based судья федерации (MVP). Ноль LLM. PASS/FIX/ESCALATE — заимствованные явные состояния
(advisor-orchestrator-worker): PASS = заземлён, FIX = редиспатч/доработка, ESCALATE = нет кандидата."""
import re

_DIVERGENCE_THRESHOLD = 0.5


def _tokens(text):
    return set(re.findall(r"[a-zа-я0-9]+", (text or "").lower()))


def _quote_statuses(cand):
    return [q.get("status", "🟡") for q in (cand or {}).get("quotes", [])]


def score_candidate(cand):
    """Рубрика репрезентанта: 🔵×10 + 🟢×3 + (есть непустой аргумент → 1)."""
    st = _quote_statuses(cand)
    blue = st.count("🔵")
    green = st.count("🟢")
    has_arg = 1 if (cand or {}).get("argument", "").strip() else 0
    return blue * 10 + green * 3 + has_arg


def _jaccard(a, b):
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 1.0


def divergence(cands):
    """Расхождение аргументов = 1 − средняя попарная Jaccard-схожесть токенов.
    <2 кандидатов → low. Сохраняем ЧИСЛО (не схлопываем в best-of-N)."""
    toks = [_tokens(c.get("argument", "")) for c in cands]
    if len(toks) < 2:
        return {"score": 0.0, "level": "low", "flagged": False}
    sims = []
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            sims.append(_jaccard(toks[i], toks[j]))
    mean_sim = sum(sims) / len(sims)
    score = round(1.0 - mean_sim, 4)
    level = "high" if score >= _DIVERGENCE_THRESHOLD else "low"
    return {"score": score, "level": level, "flagged": level == "high"}


def verdict(cand):
    """PASS — есть 🔵; FIX — кандидат есть, но не заземлён (нет 🔵); ESCALATE — кандидата нет."""
    if cand is None:
        return "ESCALATE"
    st = _quote_statuses(cand)
    if "🔵" in st:
        return "PASS"
    return "FIX"
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_judge.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/judge.py tests/test_federation_judge.py
git commit -m "feat(federation): rule-based судья — score/divergence(сохранение разнообразия)/verdict PASS-FIX-ESCALATE"
```
(with trailers)

---

### Task 3: Executor — `claim_brief` + `heartbeat_task`

**Files:**
- Create: `scripts/federation/executor.py`
- Test: `tests/test_federation_executor.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_executor.py -q`
Expected: FAIL (`ModuleNotFoundError: federation.executor`).

- [ ] **Step 3: Implement `scripts/federation/executor.py`** (this task adds claim/heartbeat; submit is Task 4)

```python
"""Исполнитель-поверхность: воркер (отдельная сессия) забирает роль-таск, играет советника на
СВОЕЙ модели, кладёт СЫРОГО кандидата. Trust-boundary (заимствование advisor-orchestrator-worker):
бриф — самодостаточные ДАННЫЕ, никогда не интерполируется в shell; воркер маркеры верности НЕ
ставит (их вычисляет наш сервер централизованно на assemble)."""

MAX_ARGUMENT = 8000
MAX_QUOTES = 30
MAX_QUOTE = 2000


def claim_brief(backend, worker_id, roles=None, timeout=1.0):
    """Блокирующий claim → структурный бриф или {'empty': True} по таймауту."""
    c = backend.claim(worker_id, roles=roles, block=True, timeout=timeout)
    if c is None:
        return {"empty": True}
    return {"task_id": c.task_id, "claim_token": c.claim_token,
            "role": c.role, "advisor_dir": c.advisor_dir, "question": c.question}


def heartbeat_task(backend, task_id, worker_id, claim_token):
    """Продлить lease. stale claim_token → {'stale': True}."""
    return backend.heartbeat(task_id, worker_id, claim_token)
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_executor.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/executor.py tests/test_federation_executor.py
git commit -m "feat(federation): executor claim_brief(структурный бриф)+heartbeat_task"
```
(with trailers)

---

### Task 4: Executor — `submit_candidate` with validation

**Files:**
- Modify: `scripts/federation/executor.py`
- Test: `tests/test_federation_executor.py`

- [ ] **Step 1: Write the failing test** (append)

```python
from federation.executor import submit_candidate


def test_submit_valid_candidate_stored_raw(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    cand = {"argument": "Сохраняй спокойствие.", "quotes": [{"text": "Confine thyself"}]}
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "claude-sonnet-5", cand)
    assert r.get("ok") is True
    rows = q.results("s1")
    stored = rows[0]["result"]
    assert stored["argument"] == "Сохраняй спокойствие."
    assert stored["quotes"] == [{"text": "Confine thyself"}]   # только text — без маркеров
    assert stored["worker_model"] == "claude-sonnet-5"         # model identity сохранена


def test_submit_stale_claim_token_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", "wrong-token", "m",
                         {"argument": "x", "quotes": []})
    assert r.get("rejected")
    assert q.results("s1") == []                               # ничего не записано (не done)


def test_submit_oversize_argument_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": "x" * 9000, "quotes": []})
    assert r.get("rejected") and "argument" in r["rejected"]


def test_submit_non_string_argument_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": {"nope": 1}, "quotes": []})
    assert r.get("rejected")


def test_submit_control_chars_sanitized(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": "clean\x07here\ttab", "quotes": [{"text": "ok\x00bye"}]})
    assert r.get("ok") is True
    stored = q.results("s1")[0]["result"]
    assert "\x07" not in stored["argument"] and "\t" in stored["argument"]  # \x07 срезан, \t цел
    assert "\x00" not in stored["quotes"][0]["text"]


def test_submit_too_many_quotes_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": "x", "quotes": [{"text": "t"}] * 40})
    assert r.get("rejected") and "quotes" in r["rejected"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_executor.py -q`
Expected: FAIL (`ImportError: cannot import name 'submit_candidate'`).

- [ ] **Step 3: Implement** — append to `scripts/federation/executor.py`

```python
import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")   # управляющие, КРОМЕ \t(09) \n(0a) \r(0d)


def _clean_text(s, maxlen, field):
    """str-проверка + лимит длины (reject) + срез управляющих (sanitize)."""
    if not isinstance(s, str):
        raise ValueError("%s: ожидалась строка" % field)
    if len(s) > maxlen:
        raise ValueError("%s: превышен лимит %d" % (field, maxlen))
    return _CTRL.sub("", s)


def _validate_candidate(cand, worker_model):
    if not isinstance(cand, dict):
        raise ValueError("candidate: ожидался объект")
    if not isinstance(worker_model, str) or not worker_model.strip():
        raise ValueError("worker_model: ожидалась непустая строка")
    argument = _clean_text(cand.get("argument", ""), MAX_ARGUMENT, "argument")
    quotes_in = cand.get("quotes", [])
    if not isinstance(quotes_in, list):
        raise ValueError("quotes: ожидался список")
    if len(quotes_in) > MAX_QUOTES:
        raise ValueError("quotes: превышен лимит %d" % MAX_QUOTES)
    quotes = []
    for i, qd in enumerate(quotes_in):
        if not isinstance(qd, dict):
            raise ValueError("quotes[%d]: ожидался объект" % i)
        quotes.append({"text": _clean_text(qd.get("text", ""), MAX_QUOTE, "quotes[%d].text" % i)})
    return {"argument": argument, "quotes": quotes, "worker_model": worker_model}


def submit_candidate(backend, task_id, worker_id, claim_token, worker_model, candidate):
    """Валидировать сырьё воркера → ack. Маркеры верности НЕ ставим (сервер сверит на assemble).
    Невалидно → {'rejected': причина}; stale claim_token → {'rejected': 'stale ...'}."""
    try:
        result = _validate_candidate(candidate, worker_model)
    except ValueError as e:
        return {"rejected": str(e)}
    ack = backend.ack(task_id, worker_id, claim_token, result)
    if ack.get("stale"):
        return {"rejected": "stale claim_token"}
    return {"ok": True}
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_executor.py -q`
Expected: PASS (all executor tests, ~9).

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/executor.py tests/test_federation_executor.py
git commit -m "feat(federation): executor submit_candidate — валидация(размер/типы/control-chars) + сырьё через ack"
```
(with trailers)

---

### Task 5: Coordinator — `open_session` + `poll_session`

**Files:**
- Create: `scripts/federation/coordinator.py`
- Test: `tests/test_federation_coordinator.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_coordinator.py -q`
Expected: FAIL (`ModuleNotFoundError: federation.coordinator`).

- [ ] **Step 3: Implement `scripts/federation/coordinator.py`** (open+poll; assemble is Tasks 6-7)

```python
"""Координатор совета-федерации: разложить план в роль-таски (по N реплик на роль), опросить статус,
собрать кандидатов. Верность сверяет НАШ сервер централизованно (Tasks 6-7)."""
from federation.queue import RoleTask


def open_session(backend, session_id, plan, replicas_default=3):
    """plan = [{role, advisor_dir, question, replicas?}]. На каждую роль кладём `replicas` тасков."""
    enqueued = 0
    roles = []
    for item in plan:
        n = int(item.get("replicas", replicas_default))
        for _ in range(n):
            backend.enqueue(RoleTask(session_id, item["role"], item["advisor_dir"],
                                     item["question"]))
        enqueued += n
        roles.append({"role": item["role"], "replicas": n})
    return {"session_id": session_id, "enqueued": enqueued, "roles": roles}


def poll_session(backend, session_id):
    """Счётчики состояний сессии (pending/claimed/done/dead)."""
    return backend.status(session_id)
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_coordinator.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/coordinator.py tests/test_federation_coordinator.py
git commit -m "feat(federation): coordinator open_session(реплики ролей)+poll_session"
```
(with trailers)

---

### Task 6: Coordinator — `assemble` (centralized fidelity + divergence + model identity)

**Files:**
- Modify: `scripts/federation/coordinator.py`
- Test: `tests/test_federation_coordinator.py`

- [ ] **Step 1: Write the failing test** (append)

```python
from federation.coordinator import assemble


def _seed_done(q, session_id, role, advisor_dir, question, argument, quote_texts, model):
    from federation.executor import claim_brief, submit_candidate
    b = claim_brief(q, "w-" + model, roles=[role], timeout=1.0)
    assert b.get("role") == role
    cand = {"argument": argument, "quotes": [{"text": t} for t in quote_texts]}
    submit_candidate(q, b["task_id"], b["worker_id"] if "worker_id" in b else "w-" + model,
                     b["claim_token"], model, cand)


def _fake_verify(quote, advisor_dir):
    # мок централизованного гейта: только точный «REAL» в правильном корпусе → 🔵
    if quote == "REAL" and advisor_dir == "advisors/aurelius":
        return {"status": "🔵", "verbatim": True, "source": "Meditations 7.29"}
    return {"status": "🟡", "verbatim": False, "source": ""}


def test_assemble_server_reverifies_and_downgrades_fake_blue(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 1}])
    # воркер кладёт цитату, которую МОГ БЫ пометить 🔵 — но сервер верит только своему verify
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "Спокойствие.", ["FAKE"], "m1")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert role0["representative"]["quotes"][0]["status"] == "🟡"   # фейк-🔵 понижен сервером


def test_assemble_preserves_divergence_and_model_identity(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 3}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now", ["REAL"], "claude-sonnet-5")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "wait gather evidence first", ["REAL"], "gemini-3")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "abandon project entirely instead", [], "gpt-5")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert len(role0["replicas"]) == 3                          # НЕ схлопнуто в best-of-N
    assert role0["divergence"]["level"] == "high" and role0["divergence"]["flagged"] is True
    assert set(role0["worker_models"]) == {"claude-sonnet-5", "gemini-3", "gpt-5"}  # identity
    # репрезентант выбран рубрикой (у заземлённых 🔵 балл выше пустого)
    assert role0["representative"]["argument"] in ("ship the mvp now", "wait gather evidence first")
    assert role0["verdict"] == "PASS"                           # есть 🔵 → PASS


def test_assemble_agreeing_replicas_low_divergence(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 2}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now", ["REAL"], "m1")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now", ["REAL"], "m2")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    assert out["roles"][0]["divergence"]["level"] == "low"
    assert out["diversity"] == "full"
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_coordinator.py -q`
Expected: FAIL (`ImportError: cannot import name 'assemble'`).

- [ ] **Step 3: Implement** — append to `scripts/federation/coordinator.py`

```python
from federation import judge as _judge


def _verify_candidate(raw, advisor_dir, verify_fn):
    """Сервер сверяет КАЖДУЮ цитату по ДОВЕРЕННОМУ advisor_dir (из строки таска). Маркеры воркера
    игнорируются — статус ставит только verify_fn (централизованный гейт)."""
    vq = []
    for q in raw.get("quotes", []):
        fc = verify_fn(q.get("text", ""), advisor_dir)
        vq.append({"text": q.get("text", ""), "status": fc.get("status", "🟡"),
                   "source": fc.get("source", "")})
    return {"argument": raw.get("argument", ""), "worker_model": raw.get("worker_model", ""),
            "quotes": vq}


def _assemble_role(role, advisor_dir, rows, verify_fn):
    cands = [_verify_candidate(r["result"], advisor_dir, verify_fn)
             for r in rows if r.get("result")]
    rep = max(cands, key=_judge.score_candidate) if cands else None
    return {"role": role, "advisor_dir": advisor_dir,
            "representative": rep, "replicas": cands,
            "divergence": _judge.divergence(cands),
            "worker_models": [c["worker_model"] for c in cands],
            "verdict": _judge.verdict(rep)}


def assemble(backend, session_id, verify_fn):
    """Собрать совет: сгруппировать по роли, сервер-сверить верность, сохранить дивергенцию и
    идентичность моделей. verify_fn(quote, advisor_dir)->{status,source} инъектируется (наш гейт)."""
    all_rows = backend.results(session_id, status=None)
    done = [r for r in all_rows if r["status"] == "done"]
    # порядок ролей — по первому появлению в сессии; advisor_dir доверенный (из строки таска)
    order, meta = [], {}
    for r in all_rows:
        if r["role"] not in meta:
            meta[r["role"]] = r["advisor_dir"]
            order.append(r["role"])
    roles_out = []
    degraded = []
    for role in order:
        rows = [r for r in done if r["role"] == role]
        if not rows:
            degraded.append(role)
            roles_out.append({"role": role, "advisor_dir": meta[role], "degraded": True,
                              "mode": "host_single_brain", "diversity": "reduced",
                              "verdict": "ESCALATE", "representative": None, "replicas": []})
            continue
        roles_out.append(_assemble_role(role, meta[role], rows, verify_fn))
    return {"session_id": session_id, "roles": roles_out, "degraded_roles": degraded,
            "diversity": "reduced" if degraded else "full"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_coordinator.py -q`
Expected: PASS (all coordinator tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/federation/coordinator.py tests/test_federation_coordinator.py
git commit -m "feat(federation): coordinator.assemble — централизованная верность + дивергенция + model identity"
```
(with trailers)

---

### Task 7: Coordinator — degrade path (empty role → host_single_brain)

**Files:**
- Test: `tests/test_federation_coordinator.py` (assemble degrade already coded in Task 6 — this task PROVES it explicitly and locks it with a focused test)

- [ ] **Step 1: Write the failing test** (append) — this asserts the degrade contract in isolation

```python
def test_assemble_degrades_role_with_no_done_candidates(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 2}])
    # ни одного submit → роль пуста
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert role0["degraded"] is True
    assert role0["mode"] == "host_single_brain"
    assert role0["diversity"] == "reduced"
    assert role0["verdict"] == "ESCALATE"
    assert role0["representative"] is None and role0["replicas"] == []
    assert out["diversity"] == "reduced" and "aurelius" in out["degraded_roles"]


def test_assemble_mixed_some_degraded_some_full(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [
        {"role": "aurelius", "advisor_dir": "advisors/aurelius", "question": "Q", "replicas": 1},
        {"role": "machiavelli", "advisor_dir": "advisors/machiavelli", "question": "Q", "replicas": 1}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship now", ["REAL"], "m1")
    # machiavelli не отвечает → деградирует, aurelius полон
    out = assemble(q, "s1", verify_fn=_fake_verify)
    by_role = {r["role"]: r for r in out["roles"]}
    assert by_role["aurelius"].get("degraded") is not True
    assert by_role["machiavelli"]["degraded"] is True
    assert out["diversity"] == "reduced"                      # хоть одна деградировала
    assert out["degraded_roles"] == ["machiavelli"]
```

- [ ] **Step 2: Run to verify it passes** (Task-6 assemble already implements degrade; these lock the contract)

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_coordinator.py -q`
Expected: PASS. If either NEW test fails, the degrade branch in `assemble` (Task 6, Step 3) is wrong — fix `_assemble_role`/`assemble` until green (do NOT weaken the test).

- [ ] **Step 3: Commit**

```bash
git add tests/test_federation_coordinator.py
git commit -m "test(federation): degrade-контракт assemble — пустая роль→host_single_brain, diversity reduced"
```
(with trailers)

---

### Task 8: MCP wiring — 6 `federation_*` handlers + TOOLS + backend singleton

**Files:**
- Modify: `scripts/mcp_server.py`
- Test: `tests/test_federation_mcp.py` (create)

**Context:** `TOOLS` is a dict `{name: {"description", "input_schema", "handler"}}` near line 1365; `_obj(props, required)` builds a JSON-schema object; `dispatch(name, args)` = `TOOLS[name]["handler"](**args)`; `_fidelity_check(quote, advisor_dir)` is defined near line 61. Add handlers + a lazy backend. `.consilium/` is gitignored.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_mcp.py -q`
Expected: FAIL (`AttributeError`/`KeyError` — tools/`_fed_backend` not defined).

- [ ] **Step 3: Implement** — in `scripts/mcp_server.py`, add near the other helper handlers (before the `TOOLS = {` block). First ensure `federation` is importable — the scripts dir is already on `sys.path` when the server runs; add at top of file with the other imports if needed: `from federation.coordinator import open_session as _fed_open, poll_session as _fed_poll, assemble as _fed_assemble` / `from federation.executor import claim_brief as _fed_claim, submit_candidate as _fed_submit, heartbeat_task as _fed_hb`.

```python
# ── Tier-2 федерация: MCP-поверхность (стейт в .consilium/, gitignored, приватно) ──
_FED_BACKEND = None


def _make_fed_backend(db_path):
    from federation.queue import SqliteBackend
    return SqliteBackend(db_path)


def _fed_backend():
    """Ленивый singleton бэкенда федерации в .consilium/federation.sqlite3 (никогда не шипается)."""
    global _FED_BACKEND
    if _FED_BACKEND is None:
        path = os.path.join(_root(), ".consilium", "federation.sqlite3")
        _FED_BACKEND = _make_fed_backend(path)
    return _FED_BACKEND


def _federation_open(session_id, plan, replicas_default=3):
    return _fed_open(_fed_backend(), session_id, plan, replicas_default)


def _federation_poll(session_id):
    return _fed_poll(_fed_backend(), session_id)


def _federation_assemble(session_id):
    # централизованный гейт: наш _fidelity_check инъектится как verify_fn (воркер не сертифицирует)
    return _fed_assemble(_fed_backend(), session_id, verify_fn=_fidelity_check)


def _federation_claim(worker_id, roles=None, timeout=1.0):
    return _fed_claim(_fed_backend(), worker_id, roles, timeout)


def _federation_submit(task_id, worker_id, claim_token, worker_model, candidate):
    return _fed_submit(_fed_backend(), task_id, worker_id, claim_token, worker_model, candidate)


def _federation_heartbeat(task_id, worker_id, claim_token):
    return _fed_hb(_fed_backend(), task_id, worker_id, claim_token)
```

Add these entries INSIDE the `TOOLS = { ... }` dict (before the closing `}`):
```python
    "federation_open": {
        "description": "Координатор совета-федерации: разложить план ролей в очередь по N реплик "
                       "(многомозговый совет — исполнители играют роли на СВОИХ моделях). plan = "
                       "[{role, advisor_dir, question, replicas?}]. Стейт локально в .consilium/. "
                       "Personal/attended (см. docs/FEDERATION.md).",
        "input_schema": {"type": "object",
                         "properties": {"session_id": {"type": "string"},
                                        "plan": {"type": "array"},
                                        "replicas_default": {"type": "integer"}},
                         "required": ["session_id", "plan"]},
        "handler": _federation_open,
    },
    "federation_poll": {
        "description": "Статус сессии-федерации: счётчики pending/claimed/done/dead. Опрашивай, "
                       "пока роли набирают кандидатов, затем federation_assemble.",
        "input_schema": _obj({"session_id": "string"}, ["session_id"]),
        "handler": _federation_poll,
    },
    "federation_assemble": {
        "description": "Собрать совет: сгруппировать кандидатов по роли, СЕРВЕР сверяет верность "
                       "цитат централизованно (воркер не сертифицирует 🔵), сохранить дивергенцию "
                       "(не best-of-N) + идентичность моделей. Пустая роль → host_single_brain "
                       "(diversity reduced). verdict PASS/FIX/ESCALATE.",
        "input_schema": _obj({"session_id": "string"}, ["session_id"]),
        "handler": _federation_assemble,
    },
    "federation_claim": {
        "description": "Исполнитель забирает роль-таск (блокирующе до timeout) → структурный бриф "
                       "{task_id, claim_token, role, advisor_dir, question} или {empty}. Сыграй "
                       "advisor_dir на СВОЕЙ модели, цитаты через cite, затем federation_submit.",
        "input_schema": {"type": "object",
                         "properties": {"worker_id": {"type": "string"},
                                        "roles": {"type": "array"},
                                        "timeout": {"type": "number"}},
                         "required": ["worker_id"]},
        "handler": _federation_claim,
    },
    "federation_submit": {
        "description": "Исполнитель кладёт СЫРОГО кандидата {argument, quotes:[{text}]} + worker_model "
                       "(своя модель). Валидация размер/типы/control-chars; маркеры НЕ ставь — сервер "
                       "сверит на assemble. stale claim_token → отклонён.",
        "input_schema": {"type": "object",
                         "properties": {"task_id": {"type": "string"},
                                        "worker_id": {"type": "string"},
                                        "claim_token": {"type": "string"},
                                        "worker_model": {"type": "string"},
                                        "candidate": {"type": "object"}},
                         "required": ["task_id", "worker_id", "claim_token", "worker_model", "candidate"]},
        "handler": _federation_submit,
    },
    "federation_heartbeat": {
        "description": "Исполнитель продлевает lease роль-таска (task_id, worker_id, claim_token), "
                       "пока играет роль. stale → задача уже переназначена.",
        "input_schema": _obj({"task_id": "string", "worker_id": "string", "claim_token": "string"},
                             ["task_id", "worker_id", "claim_token"]),
        "handler": _federation_heartbeat,
    },
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_mcp.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/mcp_server.py tests/test_federation_mcp.py
git commit -m "feat(federation): MCP-поверхность — 6 federation_* тулов + backend singleton(.consilium) + гейт-инъекция"
```
(with trailers)

---

### Task 9: INSTRUCTIONS worker-loop block + dark-tools guard

**Files:**
- Modify: `scripts/mcp_server.py` (INSTRUCTIONS string near line 1831)
- Test: `tests/test_no_dark_tools.py` (already exists — will start FAILING once Task 8 added 6 tools not yet in INSTRUCTIONS; this task makes it pass) + add a focused federation-surfacing test.

- [ ] **Step 1: Confirm the guard currently FAILS** (proves the 6 new tools are "dark")

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_no_dark_tools.py -q`
Expected: FAIL — `test_every_tool_is_surfaced_or_declared_internal` lists the 6 `federation_*` names as dark (they're in TOOLS from Task 8 but not yet in INSTRUCTIONS).

- [ ] **Step 2: Add a focused test** (append to `tests/test_no_dark_tools.py`)

```python
def test_federation_tools_surfaced_in_instructions():
    for name in ("federation_open", "federation_poll", "federation_assemble",
                 "federation_claim", "federation_submit", "federation_heartbeat"):
        assert name in m.INSTRUCTIONS, "%s не проведён в INSTRUCTIONS (тёмный федерация-тул)" % name
```

- [ ] **Step 3: Add the worker-loop block to INSTRUCTIONS** — inside the `INSTRUCTIONS = """..."""` string in `scripts/mcp_server.py`, append this paragraph before the closing `"""` (keep it terse and imperative, matching the surrounding style; silent-orchestration Rule 1 preserved):

```
Федерация (многомозговый совет, ОПЦИЯ — personal/attended, docs/FEDERATION.md). Координатор:
federation_open(session_id, plan) кладёт реплики ролей → federation_poll(session_id) до готовности →
federation_assemble(session_id) собирает (СЕРВЕР сверяет верность цитат централизованно, дивергенция
сохранена, идентичность моделей видна, пустая роль → host_single_brain). Исполнитель (твоя ОТДЕЛЬНАЯ
запущенная сессия): federation_claim(worker_id, roles) → сыграй advisor_dir на СВОЕЙ модели, цитаты
через cite → federation_submit(worker_model=своя модель) → повтор; federation_heartbeat пока играешь.
Маркеры 🔵 НЕ ставит воркер — их вычисляет сервер. Тихо (Rule 1).
```

- [ ] **Step 4: Run to verify both pass**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_no_dark_tools.py -q`
Expected: PASS (guard green — all 6 surfaced; focused test green).

- [ ] **Step 5: Commit**

```bash
git add scripts/mcp_server.py tests/test_no_dark_tools.py
git commit -m "feat(federation): INSTRUCTIONS worker-loop блок + гард тёмных тулов для federation_*"
```
(with trailers)

---

### Task 10: `docs/FEDERATION.md` + selfdoc regen + full-suite green

**Files:**
- Create: `docs/FEDERATION.md`
- Modify (regen): `docs/selfdoc/index.json`, `docs/MANUAL.md`
- Test: `tests/test_federation_docs.py` (create) + selfdoc freshness

- [ ] **Step 1: Write the failing test**

```python
"""docs/FEDERATION.md существует и несёт рамку personal/attended/single-machine (снятие ToS дизайном)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, "..", "docs", "FEDERATION.md")


def test_federation_doc_exists_with_framing():
    assert os.path.exists(DOC), "docs/FEDERATION.md отсутствует"
    text = open(DOC, encoding="utf-8").read().lower()
    for needle in ("personal", "attended", "single-machine"):
        assert needle in text, "нет рамки '%s' в FEDERATION.md" % needle
    # централизованная верность и дивергенция должны быть объяснены читателю
    assert "divergence" in text or "дивергенц" in text
    assert "host_single_brain" in text or "single-brain" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_docs.py -q`
Expected: FAIL (file missing).

- [ ] **Step 3: Create `docs/FEDERATION.md`**

```markdown
# Федерация совета (Tier-2) — многомозговый режим

**Что это.** Опциональный режим, где роли совета играют НЕ одна хост-модель, а несколько
отдельно запущенных тобой клиентов (Claude Code / Codex / Gemini / API-BYOK) — каждый на своей
модели. Координатор раскладывает роли по очереди, исполнители забирают их, играют советника на
своей модели и возвращают кандидата. Сервер собирает совет.

**Зачем.** Настоящее разнообразие взглядов: один и тот же вопрос отвечают разные модели, и мы
СОХРАНЯЕМ расхождение (divergence), а не схлопываем в один «лучший» ответ. Где реплики сошлись —
низкая дивергенция; где разошлись — флаг, и ты видишь спор.

**Рамка (важно — снятие ToS дизайном).** Это personal / attended / себе-в-пользу:
- Твои подписки — для ТВОИХ решений, а не бэкенд для чужого сервиса.
- Исполнители — твои доверенные сессии, которые ты сам запустил и за которыми наблюдаешь.
- Дефолт — single-machine (одна машина, локальная очередь в `.consilium/federation.sqlite3`).
- Никакого пула аккаунтов, никакой headless-автоматизации от чужого имени.

**Контур верности не размазан.** Исполнитель генерит СЫРОГО кандидата (аргумент + цитаты-строки)
на своей модели, но НЕ ставит маркеры 🔵/🟢/🟡 сам. Верность каждой цитаты сверяет НАШ сервер
централизованно, по корпусу того советника, чью роль играли (`advisor_dir` пишет координатор —
исполнитель его не подменяет). Фейковую 🔵 сервер понизит. Ров остаётся у нас.

**Как открыть воркера.** Запусти отдельную сессию клиента, дай ей роль:
`federation_claim(worker_id, roles=[...])` → сыграй `advisor_dir` → `federation_submit(worker_model=…)`.
Пока играешь — `federation_heartbeat` продлевает lease (если сессия упадёт, роль вернётся в очередь).

**Деградация честная.** Если роль никто не сыграл — сервер помечает её `host_single_brain`
(её отыграет хост-модель), а весь совет — `diversity: reduced`. Никакого молчаливого провала.

**Когда апгрейдить бэкенд.** MVP — локальный SQLite (одна машина). Интерфейс `QueueBackend` —
шов: для команды/корпорации за ним встаёт Redis/HTTP/Postgres без правок вызывающих. Это НЕ нужно
для соло-режима и намеренно не тащит инфру.

**Приватность стейта.** `.consilium/` в `.gitignore` — очередь, кандидаты и результаты никогда
не попадают в репозиторий и не шипаются со скиллом.
```

- [ ] **Step 4: Run to verify it passes + regen selfdoc**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_federation_docs.py -q`
Expected: PASS.

New test FILES were added across Part B (`test_federation_judge.py`, `test_federation_executor.py`, `test_federation_coordinator.py`, `test_federation_mcp.py`, `test_federation_docs.py`) → `test_selfdoc_fresh` will FAIL. Regenerate:
```bash
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
```

- [ ] **Step 5: Full offline suite green**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: whole suite green (federation + selfdoc). Ignore env-flaky `test_ssrf_check_passes_public_blocks_private` (1 skipped).

- [ ] **Step 6: Commit**

```bash
git add docs/FEDERATION.md tests/test_federation_docs.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "docs(federation): FEDERATION.md (personal/attended/single-machine) + selfdoc regen"
```
(with trailers)

---

## Self-Review (plan against spec, Part B)

- **Coverage:** coordinator open/poll/assemble (T5-T7), executor claim/submit/heartbeat (T3-T4), centralized fidelity via injected `verify_fn` (T6 + T8 wires `_fidelity_check`), best-of-N rubric judge PASS/FIX/ESCALATE (T2), divergence-preservation + model identity (T6), degrade host_single_brain (T7), MCP surface 6 tools (T8), INSTRUCTIONS worker loop + dark-tools guard (T9), docs/FEDERATION.md (T10), backend read-API (T1, prerequisite). All spec Part-B bullets covered.
- **Moat NOT weakened:** worker submits raw candidate only; markers computed exclusively by server `verify_fn` against the trusted `advisor_dir` from the task row (T6). Fake 🔵 downgrade test (T6) + MCP end-to-end test using real `_fidelity_check` injection (T8) both lock this.
- **Borrowings folded:** structural brief not shell-string (T3), PASS/FIX/ESCALATE naming (T2), critic/candidate shape (T4). Consistent with spec's borrowings section.
- **Type consistency:** `RoleTask(session_id, role, advisor_dir, question)` / `Claim(task_id, claim_token, role, advisor_dir, question)` used verbatim from Part A; candidate `{argument, quotes:[{text}]}` and verified `{argument, worker_model, quotes:[{text,status,source}]}` consistent T2/T4/T6/T8; `verify_fn(quote, advisor_dir)->{status,source}` consistent T6/T8; `divergence`/`verdict`/`score_candidate` signatures consistent T2/T6.
- **No placeholders:** every code step has complete code; every run step has exact command + expected outcome.
- **Offline invariant:** every run step uses the `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=...` prefix; selfdoc regen flagged in T10.
- **Firewall:** no push/merge steps; all work stays on `feat/tier2-federation`.
- **Note for executor:** in T6 test helper `_seed_done`, `claim_brief` returns a brief WITHOUT `worker_id`; the helper passes the literal `"w-"+model` as worker_id to `submit_candidate` — it must match the `worker_id` used in `claim_brief`. The helper already uses `"w-" + model` for both claim and submit — keep them identical (the `b["worker_id"] if ...` guard defensively handles either shape).
```
