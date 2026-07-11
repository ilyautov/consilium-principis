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
