"""MCP-поверхность подписочных воркеров: статус CLI и фоновый запуск sub_worker.py.

Почему фон, а не синхронно: одна реплика на подписке — 10-30 с (codex ~14 с на «ok», замер
2026-10-13), а совет = роли × бэкенды. Синхронный вызов порвал бы MCP-таймаут (~60 с) и заблокировал
однопоточный RPC-цикл сервера. Поэтому тул только поднимает отсоединённый процесс и сразу отвечает;
хост дальше ведёт обычный протокол федерации: federation_poll → federation_assemble.

Это МУТИРУЮЩИЙ и EGRESS-тул (вопрос уходит провайдерам подписок, тратится квота юзера) →
Правило 0: только с явного согласия юзера, с названными подписками.

Реестр запусков `.consilium/sub-workers.json` ({session_id: [{pid, backends, started_at, log}]})
нужен, чтобы фонового воркера можно было ОСТАНОВИТЬ (cancel_subscriptions): иначе передумавший
юзер не может прекратить трату квоты, кроме как искать pid руками. Воркер стартует лидером своей
группы процессов → отмена гасит и его CLI-детей.
"""
import datetime
import os
import subprocess
import sys

import cli_backends
from file_atomic import atomic_update_json

_HERE = os.path.dirname(os.path.abspath(__file__))
_WORKER = os.path.join(_HERE, "sub_worker.py")

REGISTRY = "sub-workers.json"
LOG_MAX_BYTES = 1024 * 1024          # лог больше — перед новым запуском режем
LOG_KEEP_BYTES = 64 * 1024           # …оставляя хвост (последние запуски — самое полезное)


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


def _rotate_log(path, max_bytes=LOG_MAX_BYTES, keep=LOG_KEEP_BYTES):
    """Лог воркера дописывается при каждом запуске (append) → без кап рос бы бесконечно."""
    try:
        if os.path.getsize(path) <= max_bytes:
            return
        with open(path, "rb") as fh:
            fh.seek(-keep, os.SEEK_END)
            tail = fh.read()
        with open(path, "wb") as fh:
            fh.write(b"[...log truncated...]\n" + tail)
    except OSError:
        pass                        # нет файла / нет прав — не повод не запускать воркера


def _registry_path(state_dir):
    return os.path.join(state_dir, REGISTRY)


def _register(state_dir, session_id, entry):
    def upd(cur):
        cur = cur if isinstance(cur, dict) else {}
        rows = cur.get(session_id)
        cur[session_id] = (rows if isinstance(rows, list) else []) + [entry]
        return cur
    atomic_update_json(_registry_path(state_dir), upd, default={}, recover_invalid=True)


def _valid_pid(pid):
    # bool — подкласс int; pid 0/1 и отрицательные у killpg значат «своя группа»/init/«все» → нельзя.
    return isinstance(pid, int) and not isinstance(pid, bool) and pid > 1


def _kill_group(pid):
    """Погасить группу процессов воркера. → "killed" | "gone". Исключение = не смогли."""
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return "killed" if r.returncode == 0 else "gone"
    import signal
    try:
        # Защита от переиспользования pid: наш воркер — лидер своей сессии (pgid == pid). Если
        # pid теперь у чужого процесса, он почти наверняка не лидер группы с тем же номером.
        if os.getpgid(pid) != pid:
            return "gone"
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "gone"
    return "killed"


def cancel_subscriptions(state_dir, session_id, killer=None):
    """Остановить фоновых подписочных воркеров сессии и вычистить их из реестра.
    → {"session_id", "cancelled": [pid], "gone": [pid], "errors": [{pid, error}]}.
    Невалидный pid в реестре (руками правленый файл) не трогаем — только вычищаем запись."""
    killer = killer or _kill_group
    out = {"session_id": session_id, "cancelled": [], "gone": [], "errors": []}
    path = _registry_path(state_dir)
    if not os.path.exists(path):
        out["note"] = "нет запущенных подписочных воркеров"
        return out

    def upd(cur):
        cur = cur if isinstance(cur, dict) else {}
        rows = cur.pop(session_id, None)
        for row in rows if isinstance(rows, list) else []:
            pid = row.get("pid") if isinstance(row, dict) else None
            if not _valid_pid(pid):
                out["errors"].append({"pid": pid, "error": "невалидный pid в реестре — пропущен"})
                continue
            try:
                res = killer(pid)
            except Exception as e:                               # noqa: BLE001
                out["errors"].append({"pid": pid, "error": "%s: %s" % (type(e).__name__, e)})
                continue
            out["gone" if res == "gone" else "cancelled"].append(pid)
        return cur
    atomic_update_json(path, upd, default={}, recover_invalid=True)
    if not (out["cancelled"] or out["gone"] or out["errors"]):
        out["note"] = "для сессии нет записанных воркеров"
    return out


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
        bad = sorted("%s=%r" % (k, v) for k, v in models.items()
                     if k not in cli_backends.BACKENDS or not cli_backends.valid_model(v))
        if bad:
            # Отказ всего запроса, а не тихий дроп: юзер просил конкретную модель — сыграть
            # дефолтом и промолчать значит выдать чужую модель за выбранную.
            return {"error": "недопустимые записи models (бэкенд из %s, имя модели "
                             "[A-Za-z0-9._:/-], до 64 символов): %s"
                             % (", ".join(cli_backends.BACKENDS), "; ".join(bad))}
        spec = ",".join("%s=%s" % (k, v) for k, v in models.items() if k in use)
        if spec:
            argv += ["--models", spec]
    os.makedirs(state_dir, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)[:80]
    log_path = os.path.join(state_dir, "sub-worker-%s.log" % safe)
    _rotate_log(log_path)
    pid = popen(argv, log_path)
    _register(state_dir, session_id, {
        "pid": pid, "backends": use, "log": log_path,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
    return {"spawned": True, "pid": pid, "backends": use, "missing": missing, "log": log_path,
            "status": st,
            "next": "federation_poll(session_id) пока pending/claimed > 0, затем federation_assemble; "
                    "передумали — federation_cancel_subscriptions(session_id)",
            "egress": "вопрос ушёл провайдерам подписок: %s" % ", ".join(use)}
