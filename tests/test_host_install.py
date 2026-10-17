"""host_install: подключение к Codex CLI и Kimi Code CLI (скилл + MCP) без касания реального $HOME.

Все каталоги — tmp_path; `codex` подменён фейковым runner'ом, который ведёт себя как codex-cli
0.161.0: `mcp add` переписывает config.toml и выбрасывает под-таблицы [mcp_servers.<имя>.*]
и комментарии (проверено вручную на временном CODEX_HOME).
"""
import functools
import json
import os
import re
import shlex
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import host_install  # noqa: E402
import install  # noqa: E402


def _toml_has_path(text, path):
    """Путь в TOML-строке: basic string экранирует «\\» (Windows-пути) — сверяем обе формы."""
    path = str(path)
    return path in text or path.replace("\\", "\\\\") in text


def _split_cmdline(line):
    """Разбор command_line так, как установщик её собирал: list2cmdline на win32, shlex иначе."""
    if sys.platform == "win32":
        import subprocess
        out, cur, quoted = [], "", False
        for ch in line:                    # хватает для наших строк: пробелы и двойные кавычки
            if ch == '"':
                quoted = not quoted
            elif ch == " " and not quoted:
                if cur:
                    out.append(cur)
                cur = ""
            else:
                cur += ch
        if cur:
            out.append(cur)
        assert subprocess.list2cmdline(out) == line
        return out
    return shlex.split(line)

NAME = host_install.NAME
FAKE_SERVER = (
    "import json, sys\n"
    "for line in sys.stdin:\n"
    "    req = json.loads(line)\n"
    "    print(json.dumps({'jsonrpc': '2.0', 'id': req['id'],\n"
    "                      'result': {'serverInfo': {'name': 'consilium-principis'}}}))\n"
    "    break\n"
)


class _Done:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class FakeCodex:
    """Минимальная модель `codex mcp add/get` поверх реального файла config.toml в tmp."""

    def __init__(self, codex_dir, fail_add=False, lie_on_get=False):
        self.config = os.path.join(codex_dir, "config.toml")
        self.calls = []
        self.fail_add = fail_add
        self.lie_on_get = lie_on_get

    def _text(self):
        try:
            return Path(self.config).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _entry(self, name):
        text = self._text()
        m = re.search(r"^\[mcp_servers\.%s\]\ncommand = (\".*?\")\nargs = (\[.*?\])$" % re.escape(name),
                      text, re.M)
        if not m:
            return None
        return json.loads(m.group(1)), json.loads(m.group(2))

    def __call__(self, argv):
        self.calls.append(list(argv))
        assert argv[0] == "/fake/bin/codex" and argv[1] == "mcp"
        if argv[2] == "get":
            entry = self._entry(argv[3])
            if not entry:
                return _Done(1, "", "Error: No MCP server named '%s' found." % argv[3])
            command, args = entry
            if self.lie_on_get and len(self.calls) > 2:
                args = ["/somewhere/else.py"]
            return _Done(0, json.dumps({"name": argv[3], "transport": {
                "type": "stdio", "command": command, "args": args}}))
        if argv[2] == "add":
            if self.fail_add:
                Path(self.config).write_text("garbage written by a crashed codex", encoding="utf-8")
                return _Done(2, "", "boom")
            name, command, args = argv[3], argv[5], argv[6:]
            kept, skip = [], False
            for line in self._text().splitlines():
                if line.startswith("#"):
                    continue                                     # codex теряет комментарии
                if line.startswith("["):
                    header = line.strip("[]")
                    skip = header == "mcp_servers." + name or header.startswith("mcp_servers.%s." % name)
                if not skip:
                    kept.append(line)
            body = "\n".join(kept).strip("\n")
            block = "[mcp_servers.%s]\ncommand = %s\nargs = %s" % (name, json.dumps(command), json.dumps(args))
            Path(self.config).parent.mkdir(parents=True, exist_ok=True)
            Path(self.config).write_text((body + "\n\n" if body else "") + block + "\n", encoding="utf-8")
            return _Done(0, "Added global MCP server '%s'." % name)
        raise AssertionError(argv)


def _which(name):
    return "/fake/bin/codex" if name == "codex" else None


def _skill(tmp_path, name="skill", server=True):
    d = tmp_path / name
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: consilium-principis\n---\n", encoding="utf-8")
    if server:
        (d / "scripts" / "mcp_server.py").write_text(FAKE_SERVER, encoding="utf-8")
    return d


STALE = """model = "o3"

# мой комментарий
[mcp_servers.other]
command = "node"
args = ["x.js"]

[mcp_servers.consilium-principis]
command = "/usr/bin/python3"
args = ["/nonexistent/old/scripts/mcp_server.py"]

[mcp_servers.consilium-principis.tools.cite]
approval_mode = "approve"

[mcp_servers.consilium-principis.tools.federation_claim]
approval_mode = "approve"

[profiles.x]
model = "gpt"
"""


# ── каталоги и план ─────────────────────────────────────────────────────────
def test_env_overrides_for_codex_and_kimi_homes(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "cx"))
    monkeypatch.setenv("KIMI_CODE_HOME", str(tmp_path / "km"))
    assert host_install.codex_home(home=str(tmp_path)) == str(tmp_path / "cx")
    assert host_install.kimi_home(home=str(tmp_path)) == str(tmp_path / "km")
    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.delenv("KIMI_CODE_HOME")
    assert host_install.codex_home(home=str(tmp_path)) == str(tmp_path / ".codex")
    assert host_install.kimi_home(home=str(tmp_path)) == str(tmp_path / ".kimi-code")


def test_plan_kimi_reuses_claude_skill_when_present(tmp_path):
    home = str(tmp_path)
    steps = host_install.plan(["kimi"], home=home, codex_dir=str(tmp_path / "c"), kimi_dir=str(tmp_path / "k"))
    assert steps[0]["copy"] is True
    assert steps[0]["skill_dir"] == str(tmp_path / "k" / "skills" / NAME)

    claude = Path(host_install.claude_skill_dir(home))
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("x", encoding="utf-8")
    steps = host_install.plan(["kimi"], home=home, kimi_dir=str(tmp_path / "k"))
    assert steps[0] == {"host": "kimi", "skill_dir": str(claude), "copy": False, "reuse": "claude",
                        "mcp": "kimi", "kimi_home": str(tmp_path / "k")}


def test_plan_all_installs_claude_and_codex_and_kimi_reuses_claude(tmp_path):
    steps = host_install.plan(list(host_install.HOSTS), home=str(tmp_path),
                              codex_dir=str(tmp_path / "c"), kimi_dir=str(tmp_path / "k"))
    assert [s["host"] for s in steps] == ["claude", "codex", "kimi"]
    assert steps[1]["skill_dir"] == str(tmp_path / "c" / "skills" / NAME)
    assert steps[2]["copy"] is False and steps[2]["skill_dir"] == steps[0]["skill_dir"]


def test_server_command_points_inside_the_host_skill_dir(tmp_path):
    command, args = host_install.server_command(str(tmp_path / "s"))
    assert command == sys.executable
    assert args == [str(tmp_path / "s" / "scripts" / "mcp_server.py")]


# ── Codex ───────────────────────────────────────────────────────────────────
def test_extract_subtables_keeps_only_our_server(tmp_path):
    text = STALE + '\n[mcp_servers."consilium-principis".env]\nX = "1"\n[mcp_servers.consilium-principis-2.tools.a]\nk = 1\n'
    got = host_install.extract_server_subtables(text)
    assert "[mcp_servers.consilium-principis.tools.cite]" in got
    assert "[mcp_servers.consilium-principis.tools.federation_claim]" in got
    assert '[mcp_servers."consilium-principis".env]' in got
    assert "other" not in got and "profiles" not in got and "consilium-principis-2" not in got
    assert "[mcp_servers.consilium-principis]\n" not in got


def test_codex_fresh_add(tmp_path):
    codex_dir = tmp_path / "codex"
    skill = _skill(tmp_path)
    fake = FakeCodex(str(codex_dir))
    res = host_install.install_codex(str(skill), codex_dir=str(codex_dir), runner=fake, which=_which)
    assert res["ok"] and res["changed"] and res["action"] == "add"
    assert fake.calls[1] == ["/fake/bin/codex", "mcp", "add", NAME, "--", sys.executable,
                             str(skill / "scripts" / "mcp_server.py")]
    assert res["backup"] is None


def test_codex_replaces_stale_path_and_restores_approval_tables(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    skill = _skill(tmp_path)
    fake = FakeCodex(str(codex_dir))
    res = host_install.install_codex(str(skill), codex_dir=str(codex_dir), runner=fake, which=_which)
    assert res["ok"] and res["action"] == "replace_stale" and res["preserved_subtables"]
    text = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert _toml_has_path(text, skill / "scripts" / "mcp_server.py")
    assert "/nonexistent/old" not in text
    assert text.count("[mcp_servers.consilium-principis.tools.cite]") == 1
    assert '[mcp_servers.consilium-principis.tools.federation_claim]\napproval_mode = "approve"' in text
    assert "[mcp_servers.other]" in text and "[profiles.x]" in text
    assert Path(res["backup"]).read_text(encoding="utf-8") == STALE    # комментарии живут в бэкапе


def test_codex_second_run_is_noop(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    skill = _skill(tmp_path)
    fake = FakeCodex(str(codex_dir))
    host_install.install_codex(str(skill), codex_dir=str(codex_dir), runner=fake, which=_which)
    before = (codex_dir / "config.toml").read_text(encoding="utf-8")
    backups = sorted(os.listdir(codex_dir))
    fake.calls.clear()
    res = host_install.install_codex(str(skill), codex_dir=str(codex_dir), runner=fake, which=_which)
    assert res["ok"] and res["changed"] is False and res["action"] == "unchanged"
    assert [c[2] for c in fake.calls] == ["get"]
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == before
    assert sorted(os.listdir(codex_dir)) == backups


def test_codex_dry_run_changes_nothing(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    fake = FakeCodex(str(codex_dir))
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir), runner=fake,
                                     which=_which, dry_run=True)
    assert res["ok"] and res["dry_run"] and res["action"] == "replace_stale"
    assert [c[2] for c in fake.calls] == ["get"]
    assert os.listdir(codex_dir) == ["config.toml"]
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == STALE


def test_codex_missing_binary_prints_exact_command_and_touches_nothing(tmp_path):
    codex_dir = tmp_path / "codex"
    skill = _skill(tmp_path, name="my skill")
    res = host_install.install_codex(str(skill), codex_dir=str(codex_dir), runner=FakeCodex(str(codex_dir)),
                                     which=lambda n: None)
    assert not res["ok"] and res["reason"] == "codex_not_found" and res["manual"]
    assert _split_cmdline(res["command_line"]) == ["codex", "mcp", "add", NAME, "--", sys.executable,
                                                str(skill / "scripts" / "mcp_server.py")]
    assert not codex_dir.exists()


def test_codex_failed_add_rolls_back_from_backup(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir),
                                     runner=FakeCodex(str(codex_dir), fail_add=True), which=_which)
    assert not res["ok"] and res["reason"] == "codex_add_failed" and res["rolled_back"]
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == STALE


def test_codex_verification_mismatch_rolls_back(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir),
                                     runner=FakeCodex(str(codex_dir), lie_on_get=True), which=_which)
    assert not res["ok"] and res["reason"] == "codex_verify_failed"
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == STALE


def test_codex_failed_fresh_add_leaves_no_config(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir),
                                     runner=FakeCodex(str(codex_dir), fail_add=True), which=_which)
    assert not res["ok"] and not (codex_dir / "config.toml").exists()


def test_codex_refuses_foreign_home_without_injected_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "env-codex"))
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(tmp_path / "other"), which=_which)
    assert not res["ok"] and res["reason"] == "codex_home_mismatch"


def test_codex_refuses_secret_bearing_command(tmp_path):
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(tmp_path / "c"),
                                     runner=FakeCodex(str(tmp_path / "c")), which=_which,
                                     python="OPENAI_API_KEY=sk-123")
    assert not res["ok"] and res["reason"] == "secret_args"
    assert "sk-123" not in json.dumps({k: v for k, v in res.items() if k not in ("command", "command_line")})


def test_check_codex_handshake_ok_and_missing_path(tmp_path):
    codex_dir = tmp_path / "codex"
    skill = _skill(tmp_path)
    fake = FakeCodex(str(codex_dir))
    host_install.install_codex(str(skill), codex_dir=str(codex_dir), runner=fake, which=_which)
    ok = host_install.check_codex(codex_dir=str(codex_dir), runner=fake, which=_which)
    assert ok["ok"], ok
    (skill / "scripts" / "mcp_server.py").unlink()
    bad = host_install.check_codex(codex_dir=str(codex_dir), runner=fake, which=_which)
    assert not bad["ok"] and "не существует" in bad["detail"]


def test_check_codex_without_entry(tmp_path):
    res = host_install.check_codex(codex_dir=str(tmp_path), runner=FakeCodex(str(tmp_path)), which=_which)
    assert not res["ok"] and "нет MCP-сервера" in res["detail"]


# ── Kimi ────────────────────────────────────────────────────────────────────
def test_kimi_writes_entry_preserving_neighbours_and_is_idempotent(tmp_path):
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    (kimi_dir / "mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "node", "args": ["a"]}},
                                                   "extra": 1}), encoding="utf-8")
    skill = _skill(tmp_path)
    res = host_install.install_kimi(str(skill), kimi_dir=str(kimi_dir))
    assert res["ok"] and res["changed"] and res["action"] == "add" and res["backup"]
    cfg = json.loads((kimi_dir / "mcp.json").read_text(encoding="utf-8"))
    assert cfg["extra"] == 1 and cfg["mcpServers"]["other"] == {"command": "node", "args": ["a"]}
    assert cfg["mcpServers"][NAME] == {"command": sys.executable,
                                       "args": [str(skill / "scripts" / "mcp_server.py")]}
    files = sorted(os.listdir(kimi_dir))
    again = host_install.install_kimi(str(skill), kimi_dir=str(kimi_dir))
    assert again["ok"] and again["changed"] is False
    assert sorted(os.listdir(kimi_dir)) == files


def test_kimi_replaces_stale_entry_with_backup(tmp_path):
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    old = {"mcpServers": {NAME: {"command": "python3", "args": ["/gone/scripts/mcp_server.py"]}}}
    (kimi_dir / "mcp.json").write_text(json.dumps(old), encoding="utf-8")
    res = host_install.install_kimi(str(_skill(tmp_path)), kimi_dir=str(kimi_dir))
    assert res["ok"] and res["action"] == "replace" and res["previous"] == old["mcpServers"][NAME]
    assert json.loads(Path(res["backup"]).read_text(encoding="utf-8")) == old


def test_kimi_bad_json_is_left_untouched(tmp_path):
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    (kimi_dir / "mcp.json").write_text("{not json", encoding="utf-8")
    res = host_install.install_kimi(str(_skill(tmp_path)), kimi_dir=str(kimi_dir))
    assert not res["ok"] and res["reason"] == "bad_json"
    assert (kimi_dir / "mcp.json").read_text(encoding="utf-8") == "{not json"
    assert os.listdir(kimi_dir) == ["mcp.json"]


def test_kimi_missing_home_and_dry_run_write_nothing(tmp_path):
    missing = host_install.install_kimi(str(_skill(tmp_path)), kimi_dir=str(tmp_path / "nope"))
    assert not missing["ok"] and missing["reason"] == "no_kimi_home"
    assert not (tmp_path / "nope").exists()
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    dry = host_install.install_kimi(str(_skill(tmp_path, "s2")), kimi_dir=str(kimi_dir), dry_run=True)
    assert dry["ok"] and dry["dry_run"] and dry["action"] == "add"
    assert os.listdir(kimi_dir) == []


def test_check_kimi_handshake(tmp_path):
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    skill = _skill(tmp_path)
    assert not host_install.check_kimi(kimi_dir=str(kimi_dir))["ok"]
    host_install.install_kimi(str(skill), kimi_dir=str(kimi_dir))
    assert host_install.check_kimi(kimi_dir=str(kimi_dir))["ok"]
    (skill / "scripts" / "mcp_server.py").write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    bad = host_install.check_kimi(kimi_dir=str(kimi_dir))
    assert not bad["ok"] and "initialize" in bad["detail"]


def test_check_kimi_against_the_real_server(tmp_path):
    """Настоящий scripts/mcp_server.py репо отвечает на initialize через путь из mcp.json."""
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    host_install.install_kimi(os.path.abspath(REPO), kimi_dir=str(kimi_dir))
    res = host_install.check_kimi(kimi_dir=str(kimi_dir), timeout=30)
    assert res["ok"], res


# ── install.py --host ───────────────────────────────────────────────────────
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))   # Path.home() на Windows
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("KIMI_CODE_HOME", str(tmp_path / "kimi"))
    monkeypatch.setenv("CONSILIUM_LANG", "ru")
    fake = FakeCodex(str(tmp_path / "codex"))
    monkeypatch.setattr(host_install, "install_codex",
                        functools.partial(host_install.install_codex, runner=fake, which=_which))
    monkeypatch.setattr(host_install, "check_codex",
                        functools.partial(host_install.check_codex, runner=fake, which=_which))
    return fake


def _fake_setup(monkeypatch, made):
    def setup(dest, in_place, setup_full, M):
        made.append(str(dest))
        (dest / "scripts").mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text("x", encoding="utf-8")
        (dest / "scripts" / "mcp_server.py").write_text(FAKE_SERVER, encoding="utf-8")
    monkeypatch.setattr(install, "setup_skill", setup)


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["install.py", *argv])
    with pytest.raises(SystemExit) as exc:
        install.main()
    return exc.value.code


def test_install_dry_run_all_hosts_changes_nothing(monkeypatch, tmp_path, capsys):
    fake = _isolate(monkeypatch, tmp_path)
    (tmp_path / "kimi").mkdir()
    made = []
    _fake_setup(monkeypatch, made)
    assert _run(monkeypatch, "--host", "all", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "План установки" in out and "codex mcp add" in out
    assert made == [] and [c[2] for c in fake.calls] == ["get"]
    assert not (tmp_path / "home").exists() and not (tmp_path / "codex").exists()
    assert os.listdir(tmp_path / "kimi") == []


def test_install_host_codex_end_to_end(monkeypatch, tmp_path, capsys):
    _isolate(monkeypatch, tmp_path)
    made = []
    _fake_setup(monkeypatch, made)
    assert _run(monkeypatch, "--host", "codex") == 0
    skill = tmp_path / "codex" / "skills" / NAME
    assert made == [str(skill)]
    assert _toml_has_path((tmp_path / "codex" / "config.toml").read_text(encoding="utf-8"),
                          skill / "scripts" / "mcp_server.py")
    out = capsys.readouterr().out
    assert "Готово" in out and "Codex CLI" in out and "initialize" in out


def test_install_host_kimi_reuses_claude_skill(monkeypatch, tmp_path, capsys):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "kimi").mkdir()
    claude = tmp_path / "home" / ".claude" / "skills" / NAME
    (claude / "scripts").mkdir(parents=True)
    (claude / "SKILL.md").write_text("x", encoding="utf-8")
    (claude / "scripts" / "mcp_server.py").write_text(FAKE_SERVER, encoding="utf-8")
    made = []
    _fake_setup(monkeypatch, made)
    assert _run(monkeypatch, "--host", "kimi") == 0
    assert made == []                                          # вторую копию не делаем
    cfg = json.loads((tmp_path / "kimi" / "mcp.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"][NAME]["args"] == [str(claude / "scripts" / "mcp_server.py")]
    assert not (tmp_path / "kimi" / "skills").exists()


def test_install_host_failure_is_not_reported_as_success(monkeypatch, tmp_path, capsys):
    _isolate(monkeypatch, tmp_path)                            # каталога Kimi нет → MCP не подключён
    _fake_setup(monkeypatch, [])
    assert _run(monkeypatch, "--host", "kimi") == 1
    out = capsys.readouterr().out
    assert "✅ Готово" not in out and "no_kimi_home" in out


def test_install_in_place_with_foreign_host_is_refused(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _run(monkeypatch, "--host", "codex", "--in-place") == 2


def test_default_host_claude_does_not_touch_host_installer(monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        raise AssertionError("--host claude не должен идти через install_hosts")
    monkeypatch.setattr(install, "install_hosts", boom)
    made = []
    monkeypatch.setattr(install, "setup_skill", lambda dest, in_place, full, M: made.append(dest))
    monkeypatch.setattr(sys, "argv", ["install.py", "--target", str(tmp_path / "t")])
    install.main()
    assert made == [tmp_path / "t"]
    assert "Перезапусти Claude Code" in capsys.readouterr().out


# ── сбои runner'а, кавычки, ротация бэкапов, кодировка ──────────────────────
def _raising_on_add(fake, exc):
    """runner, который на `mcp add` портит config.toml (как прерванный codex) и бросает exc."""
    def runner(argv):
        if argv[2] == "add":
            fake.calls.append(list(argv))
            Path(fake.config).write_text("half-written by a killed codex", encoding="utf-8")
            raise exc
        return fake(argv)
    return runner


@pytest.mark.parametrize("exc", [
    host_install.subprocess.TimeoutExpired(["codex", "mcp", "add"], 60),
    PermissionError(13, "Permission denied"),
    FileNotFoundError(2, "No such file or directory"),
])
def test_codex_add_exception_rolls_back_like_nonzero_exit(tmp_path, exc):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    fake = FakeCodex(str(codex_dir))
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir),
                                     runner=_raising_on_add(fake, exc), which=_which)
    assert not res["ok"] and res["reason"] == "codex_add_failed" and res["rolled_back"]
    assert res["error"]
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == STALE


def test_codex_add_timeout_on_fresh_install_leaves_no_config(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    fake = FakeCodex(str(codex_dir))
    exc = host_install.subprocess.TimeoutExpired(["codex"], 60)
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir),
                                     runner=_raising_on_add(fake, exc), which=_which)
    assert not res["ok"] and res["rolled_back"]
    assert not (codex_dir / "config.toml").exists()


def test_codex_get_exception_is_reported_not_raised(tmp_path):
    def runner(argv):
        raise host_install.subprocess.TimeoutExpired(argv, 60)
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(tmp_path / "c"),
                                     runner=runner, which=_which)
    assert not res["ok"] and res["reason"] == "codex_get_failed" and "таймаут" in res["error"]
    chk = host_install.check_codex(codex_dir=str(tmp_path / "c"), runner=runner, which=_which)
    assert not chk["ok"]


def test_codex_command_line_quotes_per_platform():
    cmd, args = r"C:\Program Files\Python312\python.exe", [r"C:\Users\Іван\skill dir\scripts\mcp_server.py"]
    win = host_install.codex_command_line(cmd, args, platform="win32")
    assert win == ('codex mcp add %s -- "C:\\Program Files\\Python312\\python.exe" '
                   '"C:\\Users\\Іван\\skill dir\\scripts\\mcp_server.py"' % NAME)
    assert "'" not in win                                   # одинарные кавычки cmd.exe не понимает
    posix = host_install.codex_command_line("/usr/bin/python3", ["/home/a b/it's/mcp_server.py"],
                                            platform="darwin")
    assert shlex.split(posix) == ["codex", "mcp", "add", NAME, "--", "/usr/bin/python3",
                                  "/home/a b/it's/mcp_server.py"]
    assert host_install.codex_command_line("/p", ["/s.py"], platform="linux") == \
        "codex mcp add %s -- /p /s.py" % NAME


def test_install_codex_manual_line_uses_injected_platform(tmp_path):
    skill = _skill(tmp_path, name="my skill")
    res = host_install.install_codex(str(skill), codex_dir=str(tmp_path / "c"), which=lambda n: None,
                                     runner=FakeCodex(str(tmp_path / "c")), platform="win32")
    assert res["reason"] == "codex_not_found"
    assert '"%s"' % (skill / "scripts" / "mcp_server.py") in res["command_line"]


def _stamp(i):
    return "2026010%d-120000-000000" % i


def test_prune_backups_keeps_newest_three_and_ignores_foreign_files(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("x", encoding="utf-8")
    for i in range(1, 7):
        (tmp_path / ("config.toml.bak." + _stamp(i))).write_text(str(i), encoding="utf-8")
    foreign = ["config.toml.bak", "config.toml.bak.manual", "config.toml.bak.2026-01-01",
               "other.toml.bak." + _stamp(1), "mcp.json.bak." + _stamp(1)]
    for name in foreign:
        (tmp_path / name).write_text("keep", encoding="utf-8")
    removed = host_install.prune_backups(str(cfg))
    assert sorted(os.path.basename(p) for p in removed) == ["config.toml.bak." + _stamp(i) for i in (1, 2, 3)]
    left = sorted(n for n in os.listdir(tmp_path) if n.startswith("config.toml.bak.2026010"))
    assert left == ["config.toml.bak." + _stamp(i) for i in (4, 5, 6)]
    for name in foreign:
        assert (tmp_path / name).exists()
    assert cfg.read_text(encoding="utf-8") == "x"


def test_codex_install_prunes_old_backups_but_keeps_the_fresh_one(tmp_path):
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(STALE, encoding="utf-8")
    for i in range(1, 6):
        (codex_dir / ("config.toml.bak." + _stamp(i))).write_text("old", encoding="utf-8")
    res = host_install.install_codex(str(_skill(tmp_path)), codex_dir=str(codex_dir),
                                     runner=FakeCodex(str(codex_dir)), which=_which)
    assert res["ok"] and os.path.isfile(res["backup"])
    backups = sorted(n for n in os.listdir(codex_dir) if ".bak." in n)
    assert len(backups) == 3 and os.path.basename(res["backup"]) == backups[-1]
    assert Path(res["backup"]).read_text(encoding="utf-8") == STALE


def test_kimi_install_prunes_old_backups(tmp_path):
    kimi_dir = tmp_path / "kimi"
    kimi_dir.mkdir()
    (kimi_dir / "mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    for i in range(1, 6):
        (kimi_dir / ("mcp.json.bak." + _stamp(i))).write_text("{}", encoding="utf-8")
    res = host_install.install_kimi(str(_skill(tmp_path)), kimi_dir=str(kimi_dir))
    assert res["ok"] and res["backup"] and os.path.isfile(res["backup"])
    backups = sorted(n for n in os.listdir(kimi_dir) if n.startswith("mcp.json.bak."))
    assert len(backups) == 3 and os.path.basename(res["backup"]) == backups[-1]


def test_default_runner_decodes_utf8_with_replace(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return _Done()
    monkeypatch.setattr(host_install.subprocess, "run", fake_run)
    host_install._default_runner(["codex", "mcp", "get", NAME, "--json"])
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace" and seen["text"] is True
    assert seen["timeout"] == host_install._CODEX_TIMEOUT and seen["check"] is False


def test_default_runner_survives_non_utf8_output(tmp_path):
    script = tmp_path / "emit.py"
    script.write_text("import sys; sys.stdout.buffer.write(b'ok \\xff\\xfe \\xd0\\x98')", encoding="utf-8")
    done = host_install._default_runner([sys.executable, str(script)])
    assert done.returncode == 0 and done.stdout.startswith("ok ") and done.stdout.endswith("И")
    assert "\ufffd" in done.stdout
