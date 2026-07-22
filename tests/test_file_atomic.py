import json
import multiprocessing
import os
import stat
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import file_atomic


def _increment_json_counter(path, iterations):
    """Process target: independent interpreter must share the file lock."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import file_atomic as atomic  # noqa: PLC0415
    for _ in range(iterations):
        atomic.atomic_update_json(
            path, lambda current: {"count": current.get("count", 0) + 1}, default={}
        )


def test_atomic_write_text_preserves_old_content_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "state.txt"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(
        file_atomic.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("boom")),
    )

    with pytest.raises(OSError, match="boom"):
        file_atomic.atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_json_round_trips_with_trailing_newline(tmp_path):
    target = tmp_path / "state.json"
    value = {"title": "Пример", "items": [1, 2]}

    file_atomic.atomic_write_json(target, value, indent=2, sort_keys=True)

    content = target.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert json.loads(content) == value


def test_atomic_update_json_serializes_competing_process_writers(tmp_path):
    target = tmp_path / "state.json"
    workers = [multiprocessing.Process(target=_increment_json_counter, args=(str(target), 30))
               for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {"count": 120}


def test_atomic_update_json_preserves_parseable_old_state_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"count": 1}\n', encoding="utf-8")
    monkeypatch.setattr(
        file_atomic.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("boom"))
    )

    with pytest.raises(OSError, match="boom"):
        file_atomic.atomic_update_json(
            target, lambda current: {"count": current["count"] + 1}, default={}
        )

    assert json.loads(target.read_text(encoding="utf-8")) == {"count": 1}


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_private_json_creates_private_parent_and_file_modes(tmp_path):
    target = tmp_path / ".consilium" / "decisions" / "private.json"

    file_atomic.atomic_write_json(target, {"private": True}, private=True)

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / ".consilium").stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / ".consilium" / "decisions").stat().st_mode) == 0o700
