"""Границы роста in-memory реестров MCP-сервера (утечки памяти долгоживущего процесса).

Аудит-бэклог:
  • ITEM 1: _JOBS и _PENDING_VERDICTS — module-level dict'ы, росли без капа →
    долгоживущий сервер = утечка. Проверяем, что кап держится и НОВЕЙШЕЕ выживает,
    а running-джоб не вытесняется терминальными.
  • ITEM 2: построчный stdio-цикл читал строку без лимита → патологически длинная
    строка буферизуется безгранично. Проверяем чистый size-хелпер (_line_within_limit).

Гермётично: реестры чистим руками, стейт восстанавливаем; сети/диска не трогаем.
"""
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pytest
import mcp_server as M


# ───────────────────────── ITEM 1: _JOBS кап ─────────────────────────

@pytest.fixture
def clean_jobs():
    """Изолируем глобальный реестр джобов: снимок до, восстановление после."""
    with M._JOBS_LOCK:
        saved, saved_seq = dict(M._JOBS), M._JOB_SEQ[0]
        M._JOBS.clear()
        M._JOB_SEQ[0] = 0
    yield
    with M._JOBS_LOCK:
        M._JOBS.clear()
        M._JOBS.update(saved)
        M._JOB_SEQ[0] = saved_seq


def test_jobs_cap_holds_and_keeps_newest(clean_jobs):
    """cap+N вставок терминальных джобов → len ≤ cap, новейший присутствует, старейший вытеснен."""
    cap = M._MAX_JOBS
    n = cap + 50
    ids = []
    for _ in range(n):
        r = M._start_job(lambda: None, "noop")
        ids.append(r["job_id"])
        # переводим в терминальное состояние сразу (иначе фон-поток может не успеть)
        with M._JOBS_LOCK:
            if ids[-1] in M._JOBS:
                M._JOBS[ids[-1]].update(status="done", result=None)
    with M._JOBS_LOCK:
        assert len(M._JOBS) <= cap
        assert ids[-1] in M._JOBS          # новейший жив
        assert ids[0] not in M._JOBS       # старейший вытеснен FIFO


def test_jobs_eviction_prefers_terminal_over_running(clean_jobs):
    """Running-джоб НЕ вытесняется, пока есть терминальные жертвы (вызывающий ещё опрашивает)."""
    with M._JOBS_LOCK:
        # старейший — running; забиваем реестр терминальными сверх капа
        M._JOB_SEQ[0] += 1
        running_id = "job-%d" % M._JOB_SEQ[0]
        M._JOBS[running_id] = {"status": "running", "label": "long", "result": None, "error": None}
        for _ in range(M._MAX_JOBS + 10):
            M._JOB_SEQ[0] += 1
            jid = "job-%d" % M._JOB_SEQ[0]
            M._JOBS[jid] = {"status": "done", "label": "x", "result": None, "error": None}
        M._evict_jobs_over_cap()
        assert len(M._JOBS) <= M._MAX_JOBS
        assert running_id in M._JOBS       # running пережил вытеснение терминальных


def test_job_status_survives_until_evicted(clean_jobs):
    """Свежий джоб опрашивается job_status до вытеснения (терминальная семантика)."""
    with M._JOBS_LOCK:
        M._JOB_SEQ[0] += 1
        jid = "job-%d" % M._JOB_SEQ[0]
        M._JOBS[jid] = {"status": "done", "label": "x", "result": 42, "error": None}
    assert M._job_status(jid)["result"] == 42


def test_start_job_rejects_when_all_records_are_running(clean_jobs, monkeypatch):
    """При полном реестре running-задач новую задачу не запускаем и не вытесняем старую."""
    with M._JOBS_LOCK:
        for i in range(M._MAX_JOBS):
            M._JOBS["job-%d" % i] = {
                "status": "running", "label": "long", "result": None, "error": None,
            }

    starts = []
    monkeypatch.setattr(M.threading.Thread, "start", lambda thread: starts.append(thread))

    result = M._start_job(lambda: None, "one-too-many")

    assert result == {"error": "слишком много активных фоновых задач; дождись job_status"}
    assert starts == []
    with M._JOBS_LOCK:
        assert len(M._JOBS) == M._MAX_JOBS
        assert all(job["status"] == "running" for job in M._JOBS.values())


def test_worker_ignores_record_removed_before_delayed_work_completes(clean_jobs, monkeypatch):
    """Завершение воркера не падает, если его запись уже удалена из реестра."""
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    errors = []
    real_thread = threading.Thread

    class RecordingThread:
        def __init__(self, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            def run():
                try:
                    self._target()
                except BaseException as error:
                    errors.append(error)
                finally:
                    completed.set()

            real_thread(target=run, daemon=self.daemon).start()

    def delayed():
        started.set()
        assert release.wait(timeout=1)
        return "finished"

    monkeypatch.setattr(M.threading, "Thread", RecordingThread)
    result = M._start_job(delayed, "delayed")
    assert started.wait(timeout=1)
    with M._JOBS_LOCK:
        M._JOBS.pop(result["job_id"])
    release.set()

    assert completed.wait(timeout=1)
    assert errors == []


def test_start_job_removes_record_when_thread_cannot_start(clean_jobs, monkeypatch):
    """Сбой запуска потока не оставляет невидимую running-запись в admission-реестре."""
    def cannot_start(thread):
        raise RuntimeError("thread creation failed")

    monkeypatch.setattr(M.threading.Thread, "start", cannot_start)
    with pytest.raises(RuntimeError, match="thread creation failed"):
        M._start_job(lambda: None, "will-not-run")
    with M._JOBS_LOCK:
        assert M._JOBS == {}

    starts = []
    monkeypatch.setattr(M.threading.Thread, "start", lambda thread: starts.append(thread))
    result = M._start_job(lambda: None, "admitted-after-failure")
    assert result["status"] == "running"
    assert len(starts) == 1


# ─────────────────── ITEM 1: _PENDING_VERDICTS кап ───────────────────

@pytest.fixture
def clean_verdicts():
    with M._VERDICT_LOCK:
        saved = dict(M._PENDING_VERDICTS)
        M._PENDING_VERDICTS.clear()
    yield
    with M._VERDICT_LOCK:
        M._PENDING_VERDICTS.clear()
        M._PENDING_VERDICTS.update(saved)


def test_pending_verdicts_cap_holds_and_keeps_newest(clean_verdicts):
    """cap+N nonce → len ≤ cap, новейший жив, старейший вытеснен FIFO (ближе к истечению)."""
    import time
    cap = M._MAX_PENDING_VERDICTS
    keys = []
    with M._VERDICT_LOCK:
        for i in range(cap + 40):
            k = "nonce-%05d" % i
            keys.append(k)
            M._PENDING_VERDICTS[k] = {"ts": time.time(), "advisor_dir": "/x",
                                      "question": "q", "limit": 4, "rel_threshold": 2,
                                      "candidates": [], "dropped": 0, "lang": {}}
            M._enforce_verdict_cap()
        assert len(M._PENDING_VERDICTS) <= cap
        assert keys[-1] in M._PENDING_VERDICTS
        assert keys[0] not in M._PENDING_VERDICTS


# ───────────────────── ITEM 2: stdio size-guard ─────────────────────

def test_line_within_limit_pure_helper():
    """Чистый size-хелпер: в пределах капа → True, за капом → False. Без live-сервера."""
    assert M._line_within_limit("small line\n") is True
    assert M._line_within_limit("x" * M._MAX_LINE) is True          # ровно на границе
    assert M._line_within_limit("x" * (M._MAX_LINE + 1)) is False   # за границей
    assert M._line_within_limit("y" * 100, max_len=10) is False     # кастомный кап


def test_line_limit_default_is_bounded():
    """Кап определён и вменяем (защита от DoS патологически длинной строкой)."""
    assert isinstance(M._MAX_LINE, int) and 0 < M._MAX_LINE <= 64 * 1024 * 1024
