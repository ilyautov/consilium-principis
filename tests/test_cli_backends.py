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

    def __call__(self, argv, stdin_text, cwd, timeout):
        self.calls.append({"argv": argv, "stdin": stdin_text, "cwd": cwd, "timeout": timeout,
                           "cwd_listing": os.listdir(cwd)})
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
    assert argv[argv.index("-m") + 1] == "gpt-5"


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


def test_no_tools_preamble_prepended(monkeypatch, installed):
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "x"})))
    cli_backends.generate("вопрос", "claude")
    assert fake.calls[0]["stdin"].startswith("Отвечай одним текстовым ответом")


def test_model_env_override(monkeypatch, installed):
    monkeypatch.setenv("CONSILIUM_CLAUDE_MODEL", "opus")
    fake = _use(monkeypatch, FakeRun(out=json.dumps({"result": "x"})))
    cli_backends.generate("q", "claude")
    argv = fake.calls[0]["argv"]
    assert argv[argv.index("--model") + 1] == "opus"


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
