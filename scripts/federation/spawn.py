"""MCP-поверхность подписочных воркеров: статус CLI и фоновый запуск sub_worker.py.

Почему фон, а не синхронно: одна реплика на подписке — 10-30 с (codex ~14 с на «ok», замер
2026-10-13), а совет = роли × бэкенды. Синхронный вызов порвал бы MCP-таймаут (~60 с) и заблокировал
однопоточный RPC-цикл сервера. Поэтому тул только поднимает отсоединённый процесс и сразу отвечает;
хост дальше ведёт обычный протокол федерации: federation_poll → federation_assemble.

Это МУТИРУЮЩИЙ и EGRESS-тул (вопрос уходит провайдерам подписок, тратится квота юзера) →
Правило 0: только с явного согласия юзера, с названными подписками.
"""
import os
import subprocess
import sys

import cli_backends

_HERE = os.path.dirname(os.path.abspath(__file__))
_WORKER = os.path.join(_HERE, "sub_worker.py")


def subscriptions_status(probe=False, probe_fn=None):
    """Какие подписочные CLI есть. probe=True — живой пинг каждой (тратит крошку квоты, ловит
    исчерпанный лимит/разлогин). → {"installed": [...], "backends": [{backend, installed, ok?, kind?}]}"""
    probe_fn = probe_fn or cli_backends.probe
    rows = []
    for b in cli_backends.BACKENDS:
        row = {"backend": b, "installed": cli_backends.available(b)}
        if probe and row["installed"]:
            p = probe_fn(b)
            row["ok"] = p.get("ok", False)
            if not row["ok"]:
                row["kind"], row["detail"] = p.get("kind"), p.get("detail")
        rows.append(row)
    return {"installed": [r["backend"] for r in rows if r["installed"]], "backends": rows}


def _popen(argv, log_path):
    """Отсоединённый запуск (единственная точка — монкипатчится в тестах)."""
    kw = {"stdin": subprocess.DEVNULL, "close_fds": True}
    log = open(log_path, "ab")
    kw["stdout"] = log
    kw["stderr"] = log
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                               | getattr(subprocess, "DETACHED_PROCESS", 0))
    else:
        kw["start_new_session"] = True
    try:
        return subprocess.Popen(argv, **kw).pid
    finally:
        log.close()


def run_subscriptions(queue, session_id, state_dir, backends=None, roles=None, models=None,
                      popen=None):
    """Поднять sub_worker.py для открытой сессии. Fail-closed проверки ДО запуска:
    сессия существует и в ней есть pending-реплики; бэкенды известны; хотя бы один установлен."""
    popen = popen or _popen
    st = queue.status(session_id)
    if not sum(st.values()):
        return {"error": "сессия %r не открыта — сначала federation_open" % session_id}
    if not st.get("pending"):
        return {"error": "в сессии нет свободных реплик (pending=0) — нечего играть", "status": st}
    if backends is None:
        backends = cli_backends.detect()
    if not isinstance(backends, list) or not all(isinstance(b, str) for b in backends):
        return {"error": "backends — список строк из %s" % ", ".join(cli_backends.BACKENDS)}
    unknown = [b for b in backends if b not in cli_backends.BACKENDS]
    if unknown:
        return {"error": "неизвестные бэкенды: %s; есть: %s"
                % (", ".join(unknown), ", ".join(cli_backends.BACKENDS))}
    missing = [b for b in backends if not cli_backends.available(b)]
    use = [b for b in backends if b not in missing]
    if not use:
        return {"error": "ни один из подписочных CLI не установлен", "missing": missing}
    argv = [sys.executable, _WORKER, "--session", session_id, "--backends", ",".join(use),
            "--no-assemble"]
    if roles:
        if not isinstance(roles, list) or not all(isinstance(r, str) and r for r in roles):
            return {"error": "roles — список непустых строк"}
        argv += ["--roles", ",".join(roles)]
    if models:
        if not isinstance(models, dict):
            return {"error": "models — объект {backend: model}"}
        spec = ",".join("%s=%s" % (k, v) for k, v in models.items()
                        if k in use and isinstance(v, str) and v.strip() and "," not in v)
        if spec:
            argv += ["--models", spec]
    os.makedirs(state_dir, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)[:80]
    log_path = os.path.join(state_dir, "sub-worker-%s.log" % safe)
    pid = popen(argv, log_path)
    return {"spawned": True, "pid": pid, "backends": use, "missing": missing, "log": log_path,
            "status": st,
            "next": "federation_poll(session_id) пока pending/claimed > 0, затем federation_assemble",
            "egress": "вопрос ушёл провайдерам подписок: %s" % ", ".join(use)}
