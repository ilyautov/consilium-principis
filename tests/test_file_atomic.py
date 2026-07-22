import json
import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import file_atomic


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
