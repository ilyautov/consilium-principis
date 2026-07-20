"""M8: _swallow(what, fn, default) — наблюдаемость тихих except на audit-critical сайтах.

Контракт: fn() бросает → возвращается default И строка (what + repr(e)) дописывается в
gitignored .consilium/swallow.log; fn() ок → результат, лог не появляется. Сам лог
упасть не должен (диск/права → молчок, как раньше). Применён точечно:
_append_judge_audit (потеря аудит-цепочки) и _kernel_themes (потеря recall-рычага).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import mcp_server as m


def _log_path(tmp_path):
    return os.path.join(str(tmp_path), ".consilium", "swallow.log")


def test_swallow_failure_returns_default_and_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))

    def boom():
        raise ValueError("kaput-метка")

    assert m._swallow("probe", boom, "DEF") == "DEF"
    with open(_log_path(tmp_path), encoding="utf-8") as f:
        line = f.read()
    assert "probe" in line and "ValueError" in line and "kaput-метка" in line


def test_swallow_ok_returns_result_no_log(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    assert m._swallow("probe", lambda: 42, "DEF") == 42
    assert not os.path.exists(_log_path(tmp_path))


def test_swallow_log_write_failure_still_returns_default(monkeypatch, tmp_path):
    # .consilium — ФАЙЛ (не каталог) → makedirs/open падают; хелпер обязан молча отдать default.
    (tmp_path / ".consilium").write_text("blocker", encoding="utf-8")
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    assert m._swallow("probe", lambda: 1 / 0, "DEF") == "DEF"


def test_judge_audit_failure_logged(monkeypatch, tmp_path):
    # Audit-critical сайт: путь аудита строится через corpus_path → его сбой = потеря
    # аудит-записи; False (fail-closed) + след в swallow.log.
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))

    def _broken(adv):
        raise OSError("disk gone")

    monkeypatch.setattr(m, "corpus_path", _broken)
    assert m._append_judge_audit("adv", {"x": 1}) is False
    with open(_log_path(tmp_path), encoding="utf-8") as f:
        line = f.read()
    assert "judge_audit" in line and "disk gone" in line


def test_judge_audit_ok_writes_and_no_swallow_log(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(m, "corpus_path",
                        lambda adv: os.path.join(str(tmp_path), "adv", "build", "corpus.jsonl"))
    assert m._append_judge_audit("adv", {"x": 1}) is True
    audit = os.path.join(str(tmp_path), "adv", "build", "judge_audit.jsonl")
    with open(audit, encoding="utf-8") as f:
        assert json.loads(f.readline()) == {"x": 1}
    assert not os.path.exists(_log_path(tmp_path))


def test_kernel_themes_failure_logged(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))

    def _broken(adv):
        raise OSError("fs gone")

    monkeypatch.setattr(m, "corpus_path", _broken)
    assert m._kernel_themes("adv") == []
    with open(_log_path(tmp_path), encoding="utf-8") as f:
        assert "kernel_themes" in f.read()
