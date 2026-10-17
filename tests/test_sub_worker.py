"""Воркер федерации на подписках: реальная очередь (sqlite в tmp_path), фейковые CLI и retrieve."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cli_backends  # noqa: E402
from federation import spawn, sub_worker, worker_common  # noqa: E402
from federation.coordinator import assemble, open_session  # noqa: E402
from federation.queue import SqliteBackend  # noqa: E402


@pytest.fixture
def queue(tmp_path):
    q = SqliteBackend(str(tmp_path / "fed.sqlite3"))
    yield q
    q.close()


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(cli_backends, "binary", lambda b: "/usr/bin/" + b if b in cli_backends.BACKENDS else None)


def _plan(tmp_path):
    out = []
    for slug, name in (("marcus-aurelius", None), ("my-cfo", "Финдиректор Петров")):
        d = tmp_path / slug
        d.mkdir()
        if name:
            (d / "persona.md").write_text("---\nname: %s\n---\n# x\n" % name, encoding="utf-8")
        out.append({"role": slug, "advisor_dir": str(d), "question": "Брать ли кредит?"})
    return out


def _gen(prompt, backend, model=None, timeout=None):
    return json.dumps({"argument": "%s думает: %s" % (backend, prompt.splitlines()[0]),
                       "cite_query": "fortune"})


def _retrieve(q, adir, top_k=3):
    return {"passages": [{"text": "verbatim " + os.path.basename(adir)},
                         {"text": "verbatim " + os.path.basename(adir)}]}


def test_each_backend_plays_each_role_once(queue, installed, tmp_path):
    open_session(queue, "s1", _plan(tmp_path), replicas_default=2)
    report = sub_worker.run(queue, ["claude", "codex"], ["marcus-aurelius", "my-cfo"],
                            generate_fn=_gen, retrieve_fn=_retrieve, log=lambda m: None)
    assert {b: [p["ok"] for p in v] for b, v in report.items()} == {
        "claude": [True, True], "codex": [True, True]}
    env = assemble(queue, "s1", verify_fn=lambda t, d: {"status": "🔵", "source": "x"})
    for role in env["roles"]:
        assert sorted(role["worker_models"]) == ["claude", "codex"]   # разнообразие по модели
        assert not role.get("degraded")
    assert queue.status("s1")["pending"] == 0


def test_prompt_uses_persona_name_and_quotes_are_deduped(queue, installed, tmp_path):
    open_session(queue, "s2", _plan(tmp_path), replicas_default=1)
    prompts = []

    def gen(prompt, backend, model=None, timeout=None):
        prompts.append(prompt)
        return _gen(prompt, backend)
    sub_worker.run(queue, ["claude"], ["marcus-aurelius", "my-cfo"], generate_fn=gen,
                   retrieve_fn=_retrieve, log=lambda m: None)
    assert prompts[0].startswith("Ты играешь советника: Марк Аврелий.")
    assert prompts[1].startswith("Ты играешь советника: Финдиректор Петров.")
    rows = queue.results("s2")
    assert all(len(r["result"]["quotes"]) == 1 for r in rows)     # near-dup пассаж схлопнут


def test_failed_backend_drops_out_and_replica_stays_unplayed(queue, installed, tmp_path):
    open_session(queue, "s3", _plan(tmp_path), replicas_default=2)

    def gen(prompt, backend, model=None, timeout=None):
        if backend == "kimi":
            raise cli_backends.CLIBackendError("kimi", "quota", "403")
        return _gen(prompt, backend)
    report = sub_worker.run(queue, ["claude", "kimi"], ["marcus-aurelius", "my-cfo"],
                            generate_fn=gen, retrieve_fn=_retrieve, log=lambda m: None)
    assert report["kimi"] == [{"role": "marcus-aurelius", "ok": False, "error": "quota", "detail": "403"}]
    assert [p["ok"] for p in report["claude"]] == [True, True]
    st = queue.status("s3")
    assert st["done"] == 2 and st["claimed"] == 0 and st["pending"] == 2  # nack вернул сразу
    failed = [r for r in queue.results("s3", status=None) if r["status"] == "pending"]
    assert failed                                                          # доиграет другой/хост


def test_missing_cli_reported_not_silent(queue, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_backends, "binary", lambda b: "/usr/bin/claude" if b == "claude" else None)
    open_session(queue, "s4", _plan(tmp_path), replicas_default=1)
    report = sub_worker.run(queue, ["claude", "codex"], ["marcus-aurelius"],
                            generate_fn=_gen, retrieve_fn=_retrieve, log=lambda m: None)
    assert report["codex"][0]["error"] == "missing"


def test_session_roles_in_enqueue_order(queue, tmp_path):
    open_session(queue, "s5", _plan(tmp_path), replicas_default=2)
    assert sub_worker.session_roles(queue, "s5") == ["marcus-aurelius", "my-cfo"]


def test_parse_models():
    assert sub_worker._parse_models("claude=opus, codex=gpt-5,junk,=x") == {"claude": "opus", "codex": "gpt-5"}
    assert sub_worker._parse_models("claude=--yolo,codex=a b,kimi=kimi-k2:latest") == {"kimi": "kimi-k2:latest"}


def test_parse_candidate_tolerates_fences_and_non_object():
    assert worker_common.parse_candidate('```json\n{"argument":"a","cite_query":"q"}\n```') == \
        {"argument": "a", "cite_query": "q"}
    assert worker_common.parse_candidate("просто текст")["cite_query"] == ""
    assert worker_common.parse_candidate("[1,2]")["argument"] == "[1,2]"


# --- spawn (MCP-поверхность) ------------------------------------------------------

def test_spawn_validates_before_launch(queue, installed, tmp_path):
    never = lambda argv, log: pytest.fail("не должен стартовать")  # noqa: E731
    assert "не открыта" in spawn.run_subscriptions(queue, "nope", str(tmp_path), popen=never)["error"]
    open_session(queue, "s6", _plan(tmp_path), replicas_default=1)
    assert "неизвестные" in spawn.run_subscriptions(queue, "s6", str(tmp_path), backends=["gpt"],
                                                     popen=never)["error"]
    assert "roles" in spawn.run_subscriptions(queue, "s6", str(tmp_path), backends=["claude"],
                                              roles="x", popen=never)["error"]


def test_spawn_launches_detached_worker(queue, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_backends, "binary", lambda b: "/usr/bin/claude" if b == "claude" else None)
    open_session(queue, "s 7/../x", _plan(tmp_path), replicas_default=2)
    seen = {}

    def popen(argv, log):
        seen["argv"], seen["log"] = argv, log
        return 4242
    r = spawn.run_subscriptions(queue, "s 7/../x", str(tmp_path / "state"),
                                backends=["claude", "codex"], roles=["my-cfo"],
                                models={"claude": "opus", "codex": "gpt-5"}, popen=popen)
    assert r["spawned"] and r["pid"] == 4242
    assert r["backends"] == ["claude"] and r["missing"] == ["codex"]
    argv = seen["argv"]
    assert argv[argv.index("--backends") + 1] == "claude"
    assert argv[argv.index("--models") + 1] == "claude=opus"
    assert "--no-assemble" in argv
    assert os.path.dirname(seen["log"]) == str(tmp_path / "state")   # нет path traversal в имени лога
    assert "egress" in r


def test_spawn_refuses_when_nothing_installed(queue, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_backends, "binary", lambda b: None)
    open_session(queue, "s8", _plan(tmp_path), replicas_default=1)
    r = spawn.run_subscriptions(queue, "s8", str(tmp_path), popen=lambda a, l: pytest.fail("x"))
    assert "error" in r


def test_subscriptions_status(installed):
    st = spawn.subscriptions_status()
    assert st["installed"] == ["claude", "codex", "kimi"]
    st = spawn.subscriptions_status(probe=True, probe_fn=lambda b: {"ok": b != "kimi", "kind": "quota"})
    by = {r["backend"]: r for r in st["backends"]}
    assert by["claude"]["ok"] is True and by["kimi"]["kind"] == "quota"


def test_retrieve_refusal_is_reported_not_silent(queue, installed, tmp_path):
    """Догфуд 2026-10-13: советник вне advisors/ → retrieve вернул {"error"}; воркер обязан это сказать."""
    open_session(queue, "s9", _plan(tmp_path), replicas_default=1)
    logs = []
    report = sub_worker.run(queue, ["claude"], ["marcus-aurelius"], generate_fn=_gen,
                            retrieve_fn=lambda q, d, top_k=3: {"error": "неизвестный советник"},
                            log=logs.append)
    row = report["claude"][0]
    assert row["ok"] and row["n_quotes"] == 0 and row["cite_query"] == "fortune"
    assert row["ground_errors"] == ["retrieve отказал: неизвестный советник"]
    assert any("⚠ retrieve отказал" in m for m in logs)


# --- аудит: внутренние сбои, модели, реестр PID и отмена ------------------------------

def test_internal_error_nacks_and_continues(queue, installed, tmp_path):
    """Неожиданное исключение (не CLIBackendError) не убивает поток: реплика nack'ается,
    строка {error: internal}, следующая роль играется."""
    open_session(queue, "s10", _plan(tmp_path), replicas_default=1)
    calls = []

    def gen(prompt, backend, model=None, timeout=None):
        calls.append(prompt)
        if len(calls) == 1:
            raise KeyError("boom")
        return _gen(prompt, backend)
    report = sub_worker.run(queue, ["claude"], ["marcus-aurelius", "my-cfo"], generate_fn=gen,
                            retrieve_fn=_retrieve, log=lambda m: None)
    rows = report["claude"]
    assert rows[0] == {"role": "marcus-aurelius", "ok": False, "error": "internal", "detail": "KeyError"}
    assert rows[1]["ok"] is True and rows[1]["role"] == "my-cfo"
    st = queue.status("s10")
    assert st["claimed"] == 0 and st["pending"] == 1 and st["done"] == 1


def test_internal_error_in_retrieve_is_contained(queue, installed, tmp_path):
    open_session(queue, "s11", _plan(tmp_path), replicas_default=1)

    def bad_retrieve(q, d, top_k=3):
        raise RuntimeError("индекс сломан")
    report = sub_worker.run(queue, ["claude"], ["marcus-aurelius"], generate_fn=_gen,
                            retrieve_fn=bad_retrieve, log=lambda m: None)
    row = report["claude"][0]
    # ground_via_cite может сам превратить сбой retrieve в ground_errors — оба исхода честные,
    # главное: поток жив, реплика не висит claimed.
    assert row["ok"] is True or row["error"] == "internal"
    assert queue.status("s11")["claimed"] == 0


def test_spawn_rejects_invalid_models(queue, installed, tmp_path):
    open_session(queue, "s12", _plan(tmp_path), replicas_default=1)
    never = lambda argv, log: pytest.fail("не должен стартовать")  # noqa: E731
    r = spawn.run_subscriptions(queue, "s12", str(tmp_path), backends=["claude"],
                                models={"claude": "--yolo", "evil": "x", "codex": "ok-model"}, popen=never)
    assert "недопустимые записи models" in r["error"]
    assert "claude='--yolo'" in r["error"] and "evil=" in r["error"] and "codex='" not in r["error"]


def test_spawn_registers_pid_and_cancel_kills_group(queue, installed, tmp_path):
    open_session(queue, "s13", _plan(tmp_path), replicas_default=1)
    state = tmp_path / "state"
    pids = iter([5001, 5002])
    for _ in range(2):
        r = spawn.run_subscriptions(queue, "s13", str(state), backends=["claude"],
                                    popen=lambda argv, log: next(pids))
        assert r["spawned"]
    reg = json.loads((state / "sub-workers.json").read_text(encoding="utf-8"))
    assert [e["pid"] for e in reg["s13"]] == [5001, 5002]
    assert reg["s13"][0]["backends"] == ["claude"] and reg["s13"][0]["started_at"]
    assert reg["s13"][0]["log"].endswith(".log")
    killed = []

    def killer(pid):
        killed.append(pid)
        return "gone" if pid == 5002 else "killed"
    out = spawn.cancel_subscriptions(str(state), "s13", killer=killer)
    assert killed == [5001, 5002]
    assert out["cancelled"] == [5001] and out["gone"] == [5002] and out["errors"] == []
    assert "s13" not in json.loads((state / "sub-workers.json").read_text(encoding="utf-8"))
    again = spawn.cancel_subscriptions(str(state), "s13", killer=lambda p: pytest.fail("уже вычищено"))
    assert again["cancelled"] == [] and "note" in again


def test_cancel_skips_invalid_pids_and_other_sessions(tmp_path):
    reg = {"a": [{"pid": 1}, {"pid": 0}, {"pid": -5}, {"pid": True}, {"pid": "123"}, {"pid": 777}],
           "b": [{"pid": 888}]}
    (tmp_path / "sub-workers.json").write_text(json.dumps(reg), encoding="utf-8")
    killed = []
    out = spawn.cancel_subscriptions(str(tmp_path), "a", killer=lambda p: killed.append(p) or "killed")
    assert killed == [777] and out["cancelled"] == [777] and len(out["errors"]) == 5
    left = json.loads((tmp_path / "sub-workers.json").read_text(encoding="utf-8"))
    assert left == {"b": [{"pid": 888}]}                     # чужая сессия не тронута


def test_cancel_without_registry(tmp_path):
    out = spawn.cancel_subscriptions(str(tmp_path), "nope", killer=lambda p: pytest.fail("x"))
    assert out["cancelled"] == [] and "note" in out


def test_killer_error_reported(tmp_path):
    (tmp_path / "sub-workers.json").write_text(json.dumps({"a": [{"pid": 4242}]}), encoding="utf-8")

    def boom(pid):
        raise PermissionError("not permitted")
    out = spawn.cancel_subscriptions(str(tmp_path), "a", killer=boom)
    assert out["errors"][0]["pid"] == 4242 and "PermissionError" in out["errors"][0]["error"]


@pytest.mark.skipif(os.name == "nt", reason="группы процессов POSIX")
def test_real_kill_group_terminates_worker(tmp_path):
    import subprocess
    import time
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        assert spawn._kill_group(p.pid) == "killed"
        p.wait(timeout=10)
        assert spawn._kill_group(p.pid) == "gone"
    finally:
        if p.poll() is None:
            p.kill()


def test_log_rotation_keeps_tail(tmp_path):
    log = tmp_path / "w.log"
    log.write_bytes(b"A" * (spawn.LOG_MAX_BYTES + 10) + b"TAIL-END")
    spawn._rotate_log(str(log))
    data = log.read_bytes()
    assert len(data) <= spawn.LOG_KEEP_BYTES + 64 and data.endswith(b"TAIL-END")
    small = tmp_path / "s.log"
    small.write_bytes(b"x" * 10)
    spawn._rotate_log(str(small))
    assert small.read_bytes() == b"x" * 10
    spawn._rotate_log(str(tmp_path / "missing.log"))          # нет файла — не падаем
