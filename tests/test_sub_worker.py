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
                                models={"claude": "opus", "codex": "gpt-5", "evil": "x,y"}, popen=popen)
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
