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
