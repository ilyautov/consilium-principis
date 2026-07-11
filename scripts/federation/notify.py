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
