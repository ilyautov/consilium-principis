"""config_set валидирует moat-критичные числовые ключи ПЕРЕД записью в board_config.json.

M7: abstain_threshold=0 (или ≤0 / ≥1) тихо отключал бы весь ров воздержания; hybrid_alpha
вне [0,1] ломает смешивание. Гейт fail-closed: невалидное значение отвергается и файл НЕ
трогается (частичная запись не должна отравить конфиг). Хермётично: _root → tmp_path.
"""
import os
import sys
import json
import stat
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import mcp_server  # noqa: E402
from mcp_server import dispatch  # noqa: E402


@pytest.fixture(autouse=True)
def _root_in_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    return tmp_path


def _cfg_path(tmp_path):
    return tmp_path / "board_config.json"


def test_valid_abstain_threshold_writes(_root_in_tmp):
    r = dispatch("config_set", {"key": "abstain_threshold", "value": 0.5})
    assert "error" not in r and r["new"] == 0.5
    on_disk = json.load(open(_cfg_path(_root_in_tmp), encoding="utf-8"))
    assert on_disk["abstain_threshold"] == 0.5


def test_config_set_recovers_from_malformed_json(_root_in_tmp):
    p = _cfg_path(_root_in_tmp)
    p.write_text("{broken", encoding="utf-8")

    result = dispatch("config_set", {"key": "retrieval_mode", "value": "hybrid"})

    assert result["old"] is None and result["new"] == "hybrid"
    assert json.loads(p.read_text(encoding="utf-8")) == {"retrieval_mode": "hybrid"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_config_file_is_private(_root_in_tmp):
    dispatch("config_set", {"key": "abstain_threshold", "value": 0.5})
    assert stat.S_IMODE(_cfg_path(_root_in_tmp).stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_swallow_state_directory_and_log_are_private(_root_in_tmp):
    result = mcp_server._swallow("test", lambda: (_ for _ in ()).throw(OSError("boom")), None)
    log = _root_in_tmp / ".consilium" / "swallow.log"
    assert result is None and log.is_file()
    assert stat.S_IMODE((_root_in_tmp / ".consilium").stat().st_mode) == 0o700
    assert stat.S_IMODE(log.stat().st_mode) == 0o600


@pytest.mark.parametrize("bad", [0, 1, -0.1, "foo"])
def test_abstain_threshold_out_of_range_rejected_and_file_unchanged(bad, _root_in_tmp):
    p = _cfg_path(_root_in_tmp)
    p.write_text(json.dumps({"abstain_threshold": 0.4}), encoding="utf-8")
    r = dispatch("config_set", {"key": "abstain_threshold", "value": bad})
    assert "error" in r and r["rejected"] == bad
    # файл НЕ изменён — прежнее валидное значение на месте
    assert json.load(open(p, encoding="utf-8"))["abstain_threshold"] == 0.4


def test_abstain_threshold_reject_does_not_create_file(_root_in_tmp):
    p = _cfg_path(_root_in_tmp)
    assert not p.exists()
    r = dispatch("config_set", {"key": "abstain_threshold", "value": 0})
    assert "error" in r
    assert not p.exists(), "отвергнутое значение не должно создавать конфиг"


def test_hybrid_alpha_out_of_range_rejected(_root_in_tmp):
    r = dispatch("config_set", {"key": "hybrid_alpha", "value": 1.5})
    assert "error" in r and r["rejected"] == 1.5
    assert not _cfg_path(_root_in_tmp).exists()


def test_hybrid_alpha_valid_writes(_root_in_tmp):
    r = dispatch("config_set", {"key": "hybrid_alpha", "value": 0.7})
    assert "error" not in r and r["new"] == 0.7
    assert json.load(open(_cfg_path(_root_in_tmp), encoding="utf-8"))["hybrid_alpha"] == 0.7


def test_hybrid_alpha_boundaries_allowed(_root_in_tmp):
    # 0 и 1 — валидные края для alpha (в отличие от abstain_threshold)
    assert "error" not in dispatch("config_set", {"key": "hybrid_alpha", "value": 0})
    assert "error" not in dispatch("config_set", {"key": "hybrid_alpha", "value": 1})


def test_non_numeric_known_key_still_writes(_root_in_tmp):
    r = dispatch("config_set", {"key": "retrieval_mode", "value": "hybrid"})
    assert "error" not in r and r["new"] == "hybrid"
    assert json.load(open(_cfg_path(_root_in_tmp), encoding="utf-8"))["retrieval_mode"] == "hybrid"


def test_unknown_key_rejected_and_file_not_written(_root_in_tmp):
    # M3 (breaking): было «писалось с warning» — теперь fail-closed reject, файл не трогается
    r = dispatch("config_set", {"key": "frobnicate", "value": 1})
    assert "error" in r and r["rejected"] == 1
    assert not _cfg_path(_root_in_tmp).exists()


def test_config_set_rejects_unknown_key(_root_in_tmp):
    # M3: fail-closed whitelist — неизвестный ключ НЕ пишется (даже с warning).
    # relevance_gate — боевой пример: {"enabled": false} молча снимал гейт цитат.
    p = _cfg_path(_root_in_tmp)
    p.write_text("{}", encoding="utf-8")
    out = mcp_server._config_set("relevance_gate", {"enabled": False})
    assert "rejected" in out or "error" in out
    assert json.load(open(p, encoding="utf-8")) == {}


def test_config_set_known_key_still_works(_root_in_tmp):
    _cfg_path(_root_in_tmp).write_text("{}", encoding="utf-8")
    out = mcp_server._config_set("retrieval_mode", "hybrid")
    assert out.get("new") == "hybrid"
