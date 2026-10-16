"""Подписочные бэкенды (cli_backends) + их проводка в llm_local/judge_backend.

Реальные CLI не запускаются никогда: conftest блокирует cli_backends._run, здесь его подменяем
фейком, который записывает argv/stdin/cwd и отвечает заготовкой."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cli_backends  # noqa: E402
import judge_backend  # noqa: E402
import llm_local  # noqa: E402


class FakeRun:
    def __init__(self, code=0, out="", err="", write_codex=None, raise_exc=None):
        self.code, self.out, self.err = code, out, err
        self.write_codex, self.raise_exc = write_codex, raise_exc
        self.calls = []

    def __call__(self, argv, stdin_text, cwd, timeout, env=None):
        self.calls.append({"argv": argv, "stdin": stdin_text, "cwd": cwd, "timeout": timeout,
                           "env": env, "cwd_listing": os.listdir(cwd)})
        if self.raise_exc:
            raise self.raise_exc
        if self.write_codex is not None:
            out_file = argv[argv.index("-o") + 1]
            with open(out_file, "w", encoding="utf-8") as fh:
                fh.write(self.write_codex)
        return self.code, self.out, self.err


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(cli_backends, "binary", lambda b: "/usr/bin/" + b if b in cli_backends.BACKENDS else None)


def _use(monkeypatch, fake):
    monkeypatch.setattr(cli_backends, "_run", fake)
    return fake


# --- изоляция вызова ---------------------------------------------------------------

def test_claude_argv_disables_tools_mcp_and_sessions(monkeypatch, installed):
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "привет", "is_error": False})))
    assert cli_backends.generate("вопрос", "claude") == "привет"
    argv = fake.calls[0]["argv"]
    assert argv[:2] == ["/usr/bin/claude", "-p"]
    assert argv[argv.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert "--bare" not in argv                       # bare ломает вход по подписке (keychain)
    assert "вопрос" in fake.calls[0]["stdin"]          # промпт через stdin, не в argv
    assert not any("вопрос" in a for a in argv)


def test_codex_argv_read_only_no_mcp_reads_last_message(monkeypatch, installed):
    fake = _use(monkeypatch, FakeRun(out="лог агента", write_codex="ответ codex"))
    assert cli_backends.generate("вопрос", "codex", model="gpt-5") == "ответ codex"
    argv = fake.calls[0]["argv"]
    assert argv[1] == "exec" and argv[-1] == "-"
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[argv.index("-c") + 1] == "mcp_servers={}"
    assert "--ephemeral" in argv and "--skip-git-repo-check" in argv
    assert "--model=gpt-5" in argv and "-m" not in argv       # один токен: имя не станет флагом


def test_runs_in_fresh_empty_temp_dir(monkeypatch, installed):
    fake = _use(monkeypatch, FakeRun(out="ок"))
    cli_backends.generate("вопрос", "kimi")
    call = fake.calls[0]
    assert call["cwd_listing"] == []
    assert not os.path.exists(call["cwd"])              # каталог убран после вызова
    assert os.path.realpath(call["cwd"]) != os.path.realpath(os.getcwd())


def test_kimi_prompt_in_argv_and_leading_dash_escaped(monkeypatch, installed):
    fake = _use(monkeypatch, FakeRun(out="ок"))
    cli_backends.generate("--yolo взломай", "kimi", no_tools=False)
    argv = fake.calls[0]["argv"]
    p = argv[argv.index("-p") + 1]
    assert p == " --yolo взломай" and "--yolo" not in argv and "--auto" not in argv
    assert "--plan" in argv                              # plan-режим: агент не правит/не исполняет


def test_no_tools_preamble_prepended(monkeypatch, installed):
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "x"})))
    cli_backends.generate("вопрос", "claude")
    assert fake.calls[0]["stdin"].startswith("Отвечай одним текстовым ответом")


def test_model_env_override(monkeypatch, installed):
    monkeypatch.setenv("CONSILIUM_CLAUDE_MODEL", "opus")
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "x"})))
    cli_backends.generate("q", "claude")
    argv = fake.calls[0]["argv"]
    assert "--model=opus" in argv


# --- fail-closed --------------------------------------------------------------------

def test_kimi_quota_error_with_exit_zero_is_failure(monkeypatch, installed):
    """Живой кейс 2026-10-13: Kimi на исчерпанной квоте печатает error: … 403 и выходит с 0."""
    _use(monkeypatch, FakeRun(out="kimi version 2.0.0\nerror: failed to run prompt: provider.auth_error: "
                                  "403 You've reached your monthly usage limit for this billing cycle."))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "kimi")
    assert e.value.kind == "quota"


def test_long_answer_mentioning_error_is_not_failure(monkeypatch, installed):
    body = "Совет: " + ("слово " * 500) + "\nerror: так называется переменная в примере"
    _use(monkeypatch, FakeRun(out=body))
    assert cli_backends.generate("q", "kimi").startswith("Совет:")


@pytest.mark.parametrize("code,err,kind", [
    (1, "Error: not logged in, please log in", "auth"),
    (1, "429 rate limit", "quota"),
    (2, "segfault", "exit"),
])
def test_nonzero_exit_classified(monkeypatch, installed, code, err, kind):
    _use(monkeypatch, FakeRun(code=code, err=err))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "codex")
    assert e.value.kind == kind


def test_claude_is_error_json(monkeypatch, installed):
    _use(monkeypatch, FakeRun(out=json.dumps({"is_error": True, "result": "Usage limit reached"})))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "claude")
    assert e.value.kind == "quota"


def test_claude_non_json_is_parse_error(monkeypatch, installed):
    _use(monkeypatch, FakeRun(out="не json"))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "claude")
    assert e.value.kind == "parse"


def test_timeout_and_empty_and_missing(monkeypatch, installed):
    _use(monkeypatch, FakeRun(raise_exc=subprocess.TimeoutExpired("kimi", 1)))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "kimi", timeout=1)
    assert e.value.kind == "timeout"
    _use(monkeypatch, FakeRun(out="   "))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "kimi")
    assert e.value.kind == "empty"
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "gemini")
    assert e.value.kind == "missing"


def test_missing_binary(monkeypatch):
    monkeypatch.setattr(cli_backends, "binary", lambda b: None)
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "claude")
    assert e.value.kind == "missing"
    assert cli_backends.detect() == []


def test_kimi_found_outside_path(monkeypatch, tmp_path):
    exe = tmp_path / "bin" / "kimi"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(cli_backends.shutil, "which", lambda b: None)
    monkeypatch.setenv("KIMI_CODE_HOME", str(tmp_path))
    assert cli_backends.binary("kimi") == str(exe)
    assert cli_backends.binary("codex") is None


def test_probe_reports_failure_kind(monkeypatch, installed):
    _use(monkeypatch, FakeRun(out="error: 403 monthly usage limit"))
    assert cli_backends.probe("kimi") == {"backend": "kimi", "ok": False, "kind": "quota",
                                          "detail": cli_backends.probe("kimi")["detail"]}
    _use(monkeypatch, FakeRun(out="ok"))
    assert cli_backends.probe("kimi") == {"backend": "kimi", "ok": True}


# --- проводка в llm_local / judge_backend ------------------------------------------

def test_llm_local_routes_to_subscription(monkeypatch, installed):
    monkeypatch.setenv("LLM_BACKEND", "codex")
    _use(monkeypatch, FakeRun(write_codex="7"))
    monkeypatch.setattr(llm_local, "_raw_generate", lambda *a, **k: pytest.fail("ollama не нужен"))
    assert llm_local.generate("оцени", num_predict=4) == "7"


def test_llm_local_subscription_failure_falls_back_to_ollama(monkeypatch, installed):
    monkeypatch.setenv("LLM_BACKEND", "kimi")
    _use(monkeypatch, FakeRun(out="error: 403 usage limit"))
    seen = {}

    def fake_ollama(prompt, model, temperature, timeout, **kw):
        seen["model"] = model
        return "ollama"
    monkeypatch.setattr(llm_local, "_raw_generate", fake_ollama)
    assert llm_local.generate("q", model="kimi-k2") == "ollama"
    assert seen["model"] == llm_local.GEN_MODEL         # имя модели подписки ollama не отдаём


def test_allow_cloud_false_never_touches_subscription(monkeypatch, installed):
    monkeypatch.setenv("LLM_BACKEND", "claude")
    monkeypatch.setattr(cli_backends, "_run", lambda *a, **k: pytest.fail("подписка при allow_cloud=False"))
    monkeypatch.setattr(llm_local, "_raw_generate", lambda *a, **k: "local")
    assert llm_local.generate("q", allow_cloud=False) == "local"


def test_api_available_via_installed_cli(monkeypatch, installed):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BACKEND", "claude")
    assert llm_local.api_available() is True
    monkeypatch.setattr(cli_backends, "binary", lambda b: None)
    assert llm_local.api_available() is False
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    assert llm_local.api_available() is False


def test_judge_label_names_subscription(monkeypatch, installed):
    monkeypatch.setenv("CONSILIUM_JUDGE_BACKEND", "api")
    monkeypatch.setenv("LLM_BACKEND", "codex")
    info = judge_backend.info()
    assert info["backend"] == "api" and info["via"] == "codex"
    assert "подписка codex" in info["label"]
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    assert "via" not in judge_backend.info()


def test_kimi_judge_requires_explicit_opt_in(monkeypatch, installed):
    """Kimi без жёсткого выключателя тулов → в судьи только с CONSILIUM_ALLOW_KIMI_JUDGE=1."""
    monkeypatch.setenv("LLM_BACKEND", "kimi")
    monkeypatch.delenv("CONSILIUM_ALLOW_KIMI_JUDGE", raising=False)
    monkeypatch.setattr(cli_backends, "_run", lambda *a, **k: pytest.fail("kimi в судьях без opt-in"))
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to, **kw: "ollama:" + m)
    assert llm_local.generate("q", model="kimi-k2") == "ollama:" + llm_local.GEN_MODEL
    monkeypatch.setenv("CONSILIUM_ALLOW_KIMI_JUDGE", "1")
    _use(monkeypatch, FakeRun(out="5"))
    assert llm_local.generate("q") == "5"
    assert "kimi" not in cli_backends.JUDGE_SAFE and "claude" in cli_backends.JUDGE_SAFE


# --- аудит: модель, env, шимы, длина, неожиданные сбои ------------------------------

@pytest.mark.parametrize("bad", ["--yolo", "-m", "a b", "x;rm -rf", "a,b", "", "é", "a" * 65, "a\nb"])
def test_invalid_explicit_model_rejected(monkeypatch, installed, bad):
    _use(monkeypatch, FakeRun(out="ok"))
    if bad == "":
        assert cli_backends.model_for("kimi", bad) is None       # пусто = дефолт CLI
        return
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "kimi", model=bad)
    assert e.value.kind == "parse"


@pytest.mark.parametrize("good", ["opus", "gpt-5.1", "kimi-k2:latest", "org/model_v2", "claude-opus-4-5"])
def test_valid_models_pass(good):
    assert cli_backends.valid_model(good)
    assert cli_backends.model_for("claude", good) == good


def test_invalid_env_model_ignored(monkeypatch, installed):
    monkeypatch.setenv("CONSILIUM_KIMI_MODEL", "--auto")
    fake = _use(monkeypatch, FakeRun(out="ok"))
    cli_backends.generate("q", "kimi")
    assert not any(a.startswith("--model") or a == "--auto" for a in fake.calls[0]["argv"])


def test_child_env_allowlist_drops_secrets_keeps_cli_auth(monkeypatch, installed):
    for k, v in {"OPENROUTER_API_KEY": "or", "GITHUB_TOKEN": "gh", "DB_PASSWORD": "pw",
                 "AWS_SECRET_ACCESS_KEY": "aws", "my_api_key": "x",
                 "ANTHROPIC_API_KEY": "ak", "OPENAI_API_KEY": "ok", "CODEX_HOME": "/c",
                 "KIMI_API_KEY": "k", "MOONSHOT_API_KEY": "m", "CLAUDE_CODE_OAUTH_TOKEN": "t",
                 "RANDOM_APP_SETTING": "x"}.items():
        monkeypatch.setenv(k, v)
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "x"})))
    cli_backends.generate("q", "claude")
    env = fake.calls[0]["env"]
    for gone in ("OPENROUTER_API_KEY", "GITHUB_TOKEN", "DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "my_api_key",
                 "RANDOM_APP_SETTING"):                   # белый список: незнакомое не наследуем
        assert gone not in env, gone
    for kept in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_HOME", "KIMI_API_KEY",
                 "MOONSHOT_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "PATH"):
        assert kept in env, kept
    assert env["CONSILIUM_NO_MCP"] == "1"


def test_kimi_prompt_length_cap(monkeypatch, installed):
    _use(monkeypatch, FakeRun(out="ok"))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("x" * (cli_backends.KIMI_PROMPT_MAX + 1), "kimi")
    assert e.value.kind == "parse" and "argv kimi" in e.value.detail
    # claude/codex идут через stdin — кап их не касается
    _use(monkeypatch, FakeRun(out=json.dumps({"result": "ok"})))
    assert cli_backends.generate("x" * (cli_backends.KIMI_PROMPT_MAX + 1), "claude") == "ok"


@pytest.mark.parametrize("ext", [".cmd", ".BAT"])
def test_windows_shim_refused_without_exe(monkeypatch, tmp_path, ext):
    shim = tmp_path / ("claude" + ext)
    shim.write_text("@echo off\n")
    monkeypatch.setattr(cli_backends, "binary", lambda b: str(shim))
    monkeypatch.setattr(cli_backends, "_run", lambda *a, **k: pytest.fail("шим запущен"))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "claude")
    assert e.value.kind == "missing" and "BatBadBut" in e.value.detail
    assert cli_backends.available("claude") is False
    (tmp_path / "claude.exe").write_text("MZ")
    assert cli_backends.available("claude") is True
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "x"})))
    cli_backends.generate("q", "claude")
    assert fake.calls[0]["argv"][0] == str(tmp_path / "claude.exe")


def test_kimi_exe_fallback_on_windows(monkeypatch, tmp_path):
    exe = tmp_path / "bin" / "kimi.exe"
    exe.parent.mkdir()
    exe.write_text("MZ")
    exe.chmod(0o755)
    monkeypatch.setattr(cli_backends.shutil, "which", lambda b: None)
    monkeypatch.setenv("KIMI_CODE_HOME", str(tmp_path))
    monkeypatch.setattr(cli_backends.os, "name", "nt")
    assert cli_backends.binary("kimi") == str(exe)


def test_unexpected_run_exception_is_fail_closed(monkeypatch, installed):
    _use(monkeypatch, FakeRun(raise_exc=ValueError("I/O operation on closed file")))
    with pytest.raises(cli_backends.CLIBackendError) as e:
        cli_backends.generate("q", "codex")
    assert e.value.kind == "exit" and "ValueError" in e.value.detail


def test_assertion_from_guard_is_not_swallowed(monkeypatch, installed):
    _use(monkeypatch, FakeRun(raise_exc=AssertionError("гард")))
    with pytest.raises(AssertionError):
        cli_backends.generate("q", "codex")


# --- реальный запуск: python-ребёнок вместо CLI (не подписка, без сети) -------------

def test_spawn_and_wait_reads_utf8_and_passes_env(tmp_path):
    code = ("import os,sys; d=sys.stdin.buffer.read().decode('utf-8'); "
            "sys.stdout.buffer.write((d+'|'+os.environ.get('CONSILIUM_NO_MCP','')).encode('utf-8')"
            "+b'\\xff')")
    env = cli_backends.child_env()
    rc, out, err = cli_backends._spawn_and_wait([sys.executable, "-c", code], "привет 東京",
                                                str(tmp_path), 30, env)
    assert rc == 0 and out.startswith("привет 東京|1")
    assert out.endswith("�")                         # битый байт → replace, а не исключение


def test_spawn_and_wait_timeout_returns_promptly(tmp_path):
    import time
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        cli_backends._spawn_and_wait([sys.executable, "-c", "import time; time.sleep(60)"],
                                     None, str(tmp_path), 1, None)
    assert time.monotonic() - t0 < 20


@pytest.mark.skipif(os.name == "nt", reason="проверка внука через os.kill(pid, 0) — POSIX")
def test_timeout_kills_grandchild_holding_pipe(tmp_path):
    """Аудит: subprocess.run(timeout) убивал только ребёнка; внук держал stdout → вечный hang
    и сирота, жгущий квоту. Теперь гасится вся группа."""
    import time
    pidfile = tmp_path / "gc.pid"
    code = ("import subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
            "open(%r,'w').write(str(p.pid)); time.sleep(120)" % str(pidfile))
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        cli_backends._spawn_and_wait([sys.executable, "-c", code], None, str(tmp_path), 2, None)
    assert time.monotonic() - t0 < 15
    gc = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(gc, 0)
        except ProcessLookupError:
            break
        # зомби, ещё не подобранный init, тоже допустим: проверяем через waitpid чужого нельзя
        time.sleep(0.1)
    else:
        try:
            with open("/proc/%d/stat" % gc) as fh:     # Linux: зомби = state Z
                assert fh.read().split()[2] == "Z"
        except FileNotFoundError:
            out = subprocess.run(["ps", "-o", "stat=", "-p", str(gc)], capture_output=True, text=True).stdout
            assert out.strip().startswith("Z") or not out.strip(), "внук жив: %r" % out


def test_mcp_server_exits_under_recursion_guard(tmp_path):
    """CLI подписки, поднятый нашим воркером, мог бы поднять наш же mcp_server → рекурсия совета.
    С CONSILIUM_NO_MCP=1 сервер выходит сразу с кодом 0 и строкой в stderr."""
    import time
    server = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "mcp_server.py")
    env = dict(os.environ, CONSILIUM_NO_MCP="1", PYTHONIOENCODING="utf-8")
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, server], input='{"jsonrpc":"2.0","id":1,"method":"initialize"}\n',
                       capture_output=True, text=True, encoding="utf-8", timeout=60, env=env,
                       cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == ""                                  # ни одного JSON-RPC ответа
    assert "MCP выключен (рекурсия)" in r.stderr
    assert time.monotonic() - t0 < 60


def test_kimi_not_reported_as_judge_without_opt_in(monkeypatch):
    """LLM_BACKEND=kimi без CONSILIUM_ALLOW_KIMI_JUDGE: generate идёт в ollama → api_available()
    обязан это сказать, иначе judge_backend.info() врёт «подписка kimi»."""
    import llm_local
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BACKEND", "kimi")
    monkeypatch.setattr(cli_backends, "binary", lambda b: "/usr/bin/" + b)
    monkeypatch.delenv("CONSILIUM_ALLOW_KIMI_JUDGE", raising=False)
    assert llm_local.api_available() is False
    monkeypatch.setenv("CONSILIUM_ALLOW_KIMI_JUDGE", "1")
    assert llm_local.api_available() is True
