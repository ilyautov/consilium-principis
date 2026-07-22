"""Small, neutral helpers for atomically publishing text files."""
import json
import os
from pathlib import Path
import tempfile


def atomic_write_text(path, text, *, encoding="utf-8") -> None:
    """Write *text* to *path*, preserving the previous file on failure."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(
    path, obj, *, ensure_ascii=False, indent=2, sort_keys=False
) -> None:
    """Serialize *obj* as JSON and publish it atomically with a final newline."""
    atomic_write_text(
        path,
        json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent, sort_keys=sort_keys) + "\n",
    )
