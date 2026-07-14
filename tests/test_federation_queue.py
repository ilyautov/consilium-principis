"""Субстрат очереди роль-тасков — domain-agnostic. SQLite single-writer, claim_token idempotency."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.queue import RoleTask, Claim, QueueBackend, SqliteBackend


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


def test_sweep_reclaims_expired_claim(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c = q.claim("w1")
    assert q.status("s1")["claimed"] == 1
    n = q.sweep(lease_seconds=0)
    assert n == 1
    assert q.status("s1")["pending"] == 1
    assert q.ack(c.task_id, "w1", c.claim_token, {"x": 1}).get("stale") is True


def test_sweep_kills_when_retry_exhausted(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?", max_attempts=1))
    q.claim("w1")
    n = q.sweep(lease_seconds=0)
    assert n == 1
    assert q.status("s1")["dead"] == 1


def test_sweep_leaves_fresh_claims(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    q.claim("w1")
    assert q.sweep(lease_seconds=9999) == 0
    assert q.status("s1")["claimed"] == 1


def test_aba_old_token_stale_after_reclaim(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c1 = q.claim("w1")
    q.sweep(lease_seconds=0)
    c2 = q.claim("w1")
    assert c2.claim_token != c1.claim_token
    assert q.ack(c1.task_id, "w1", c1.claim_token, {"x": 1}).get("stale") is True
    assert q.ack(c2.task_id, "w1", c2.claim_token, {"x": 2})["ok"] is True


# ── Авто-sweep на claim (догфуд 2026-07-14: sweep был реализован, но его никто не звал →
# упавший воркер держал роль в 'claimed' вечно, самоисцеления не было. Чиним в точке нужды:
# воркер, пришедший за работой, сперва реклеймит просроченное. Критично для автономного
# воркер-цикла, где рядом нет человека, чтобы заметить залипание.)

def test_claim_auto_reclaims_expired_lease(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c1 = q.claim("w1")                      # w1 забрал и «умер», не сделав heartbeat
    assert c1 is not None
    assert q.status("s1")["claimed"] == 1
    # w2 приходит за работой: авто-sweep на входе должен вернуть просроченную роль в очередь
    # и отдать её w2 в ЭТОМ же вызове — без внешнего звонка sweep.
    c2 = q.claim("w2", lease_seconds=0)
    assert c2 is not None, "claim обязан авто-реклеймить просроченный lease"
    assert c2.claim_token != c1.claim_token
    assert q.status("s1")["claimed"] == 1
    # ABA-инвариант держится: старый токен мёртв.
    assert q.ack(c1.task_id, "w1", c1.claim_token, {"x": 1}).get("stale") is True
    assert q.ack(c2.task_id, "w2", c2.claim_token, {"x": 2})["ok"] is True


def test_claim_auto_sweep_does_not_steal_fresh_claim(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    c1 = q.claim("w1")
    # Дефолтный lease щедрый: живой воркер, который ещё думает, роль НЕ теряет.
    assert q.claim("w2") is None, "свежий claim не должен уводиться из-под живого воркера"
    assert q.status("s1")["claimed"] == 1
    assert q.ack(c1.task_id, "w1", c1.claim_token, {"x": 1})["ok"] is True


def test_claim_auto_sweep_kills_retry_exhausted(tmp_path):
    from federation.queue import RoleTask
    q = _mk(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?", max_attempts=1))
    q.claim("w1")
    # Ретраи исчерпаны → авто-sweep хоронит роль, а не крутит её вечно.
    assert q.claim("w2", lease_seconds=0) is None
    assert q.status("s1")["dead"] == 1


def test_default_lease_is_generous_enough_for_a_thinking_model():
    from federation.queue import DEFAULT_LEASE_S
    # Модель, играющая советника, думает минуты. Слишком короткий lease = роль уводят
    # из-под живого воркера (его submit потом отлетит как stale) → дубль работы.
    assert DEFAULT_LEASE_S >= 120


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
    db = str(tmp_path / "race.sqlite3")
    q = SqliteBackend(db)
    N = 30
    for i in range(N):
        q.enqueue(RoleTask("s1", "r", "advisors/r", "Q%d" % i))
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    procs = [ctx.Process(target=_claim_worker, args=(db, "w%d" % k, out)) for k in range(4)]
    for p in procs:
        p.start()
    collected = []
    for _ in procs:
        collected += out.get(timeout=30)
    for p in procs:
        p.join(timeout=30)
    # каждый таск заклеймлен РОВНО один раз (single-writer сериализация)
    assert len(collected) == N
    assert len(set(collected)) == N


def test_returning_version_flag_present():
    from federation.queue import _HAS_RETURNING
    assert isinstance(_HAS_RETURNING, bool)


def test_no_connection_fd_leak_under_gc_disabled(tmp_path):
    # с выключенным GC utечка fd проявляется детерминированно; закрытие conn должно её снять
    import gc, os as _os, glob
    q = SqliteBackend(str(tmp_path / "leak.sqlite3"))
    gc.disable()
    try:
        def _fdcount():
            try:
                return len(_os.listdir("/dev/fd"))
            except OSError:
                return len(glob.glob("/proc/self/fd/*"))
        for i in range(60):
            q.enqueue(RoleTask("s1", "r", "advisors/r", "Q%d" % i))
            c = q.claim("w1")
            if c:
                q.ack(c.task_id, "w1", c.claim_token, {"ok": True})
            q.status("s1")
        base = _fdcount()
        for i in range(200):
            q.enqueue(RoleTask("s2", "r", "advisors/r", "Q%d" % i))
            q.status("s2")
        grown = _fdcount() - base
        assert grown < 40, "fd растёт (утечка connection): +%d" % grown
    finally:
        gc.enable()


def test_empty_roles_claims_nothing(tmp_path):
    q = SqliteBackend(str(tmp_path / "er.sqlite3"))
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Q?"))
    assert q.claim("w1", roles=[]) is None       # [] = нет подходящих ролей, не «любая»
    assert q.claim("w1", roles=None) is not None # None = любая, берёт таск


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
