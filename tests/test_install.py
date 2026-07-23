"""install.py: firewall и fail-closed на core-инсталле.

M5b: RUNTIME НЕ должен тащить приватный council/ (decisions/consults — user-data, gitignored,
     в .mcpbignore запрещён) в место установки → иначе приватное течёт наружу.
M5a: если board_init (ядро установки) упал (returncode!=0), НЕ печатать «✅ Готово» и выйти
     ненулевым кодом — молчаливый «успех» на сломанной установке недопустим.
"""
import os
import sys
from pathlib import Path
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO)

import install  # noqa: E402


# ── M5b: council/ не шипуется ────────────────────────────────────────────────
def test_council_not_in_runtime():
    assert "council" not in install.RUNTIME, "приватный council/ не должен копироваться в установку"


def test_copy_runtime_does_not_ship_council_but_ships_machinery(tmp_path):
    src = tmp_path / "src"
    (src / "council" / "decisions").mkdir(parents=True)
    (src / "council" / "decisions" / "secret.json").write_text('{"private":"data"}', encoding="utf-8")
    (src / "SKILL.md").write_text("# machinery", encoding="utf-8")

    dest = tmp_path / "dest"
    install.copy_runtime(src, dest)

    assert (dest / "SKILL.md").is_file(), "машинерия (SKILL.md) должна копироваться"
    assert not (dest / "council").exists(), "приватный council/ НЕ должен утечь в установку"


# ── M5a: провал board_init не выдаётся за успех ──────────────────────────────
class _FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _install_with_board_init_rc(monkeypatch, tmp_path, rc):
    """Прогнать install.main() с фейковым subprocess.run, где board_init отдаёт заданный returncode."""
    monkeypatch.setattr(install, "copy_runtime", lambda src, dest: None)
    monkeypatch.setattr(install, "detect_semantic", lambda d: False)
    monkeypatch.setattr(install, "write_breadcrumb", lambda dest, semantic: None)

    def fake_run(cmd, **kw):
        joined = " ".join(str(c) for c in cmd)
        if "board_init.py" in joined:
            return _FakeProc(returncode=rc)
        return _FakeProc(returncode=0, stdout="")

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    dest = tmp_path / "installed"
    monkeypatch.setattr(sys, "argv", ["install.py", "--target", str(dest)])
    install.main()


def test_failed_board_init_exits_nonzero_without_gotovo(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        _install_with_board_init_rc(monkeypatch, tmp_path, rc=1)
    assert exc.value.code != 0
    out = capsys.readouterr()
    assert "Готово" not in (out.out + out.err), "нельзя рапортовать успех при упавшем board_init"


def test_successful_board_init_prints_gotovo(monkeypatch, tmp_path, capsys):
    _install_with_board_init_rc(monkeypatch, tmp_path, rc=0)  # не должно бросать
    out = capsys.readouterr()
    assert "Готово" in out.out


def test_windows_launcher_selects_python_310_and_honours_no_pause():
    batch = (Path(REPO) / "install.bat").read_text(encoding="utf-8")
    check = 'import sys; assert sys.version_info >= (3, 10)'
    assert f'py -3 -c "{check}"' in batch
    assert f'python -c "{check}"' in batch
    assert 'chcp 65001 >nul' in batch
    assert 'set "PYTHONUTF8=1"' in batch
    assert 'if not "%CONSILIUM_NO_PAUSE%"=="1" pause' in batch
    assert "python.org" in batch


def test_posix_launchers_validate_python_310_before_running_installer():
    check = "import sys; assert sys.version_info >= (3, 10)"
    for launcher in ("install.sh", "install.command"):
        text = (Path(REPO) / launcher).read_text(encoding="utf-8")
        assert check in text
        assert "Python 3.10+" in text
