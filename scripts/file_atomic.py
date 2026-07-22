"""Small, neutral helpers for locked, atomically published state files."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


_PRIVATE_DIR_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600


def _best_effort_chmod(path, mode):
    """Apply POSIX privacy bits where the platform and filesystem allow it."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_private_directory(path):
    """Create a state directory and restrict it to its owner on POSIX."""
    directory = Path(path)
    missing = []
    cursor = directory
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    directory.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        _best_effort_chmod(created, _PRIVATE_DIR_MODE)
    _best_effort_chmod(directory, _PRIVATE_DIR_MODE)


def ensure_private_file(path):
    """Restrict an already-created private state file where POSIX supports modes."""
    _best_effort_chmod(path, _PRIVATE_FILE_MODE)


def _ensure_parent(destination, private):
    """Create the parent and make newly-created private hierarchy non-world-readable."""
    parent = destination.parent
    missing = []
    cursor = parent
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    parent.mkdir(parents=True, exist_ok=True)
    if private:
        ensure_private_directory(parent)
        for directory in missing:
            _best_effort_chmod(directory, _PRIVATE_DIR_MODE)
        # A pre-existing .consilium is part of the private state hierarchy too.
        if cursor.name == ".consilium":
            _best_effort_chmod(cursor, _PRIVATE_DIR_MODE)


@contextmanager
def _file_lock(destination, private=False):
    """An advisory per-file lock, shared by independent Python processes."""
    _ensure_parent(destination, private)
    lock_path = destination.with_name(".%s.lock" % destination.name)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, _PRIVATE_FILE_MODE)
    if private:
        _best_effort_chmod(lock_path, _PRIVATE_FILE_MODE)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextmanager
def exclusive_file_lock(path, *, private=False):
    """Hold a cross-process advisory lock for a caller-defined state namespace."""
    with _file_lock(Path(path), private=private):
        yield


def _atomic_write_text_unlocked(destination, text, *, encoding, private):
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            _best_effort_chmod(temporary, _PRIVATE_FILE_MODE)
        os.replace(temporary, destination)
        if private:
            _best_effort_chmod(destination, _PRIVATE_FILE_MODE)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path, text, *, encoding="utf-8", private=False) -> None:
    """Atomically write *text* while excluding other writers of the same file."""
    destination = Path(path)
    with _file_lock(destination, private=private):
        _atomic_write_text_unlocked(destination, text, encoding=encoding, private=private)


def atomic_write_json(
    path, obj, *, ensure_ascii=False, indent=2, sort_keys=False, private=False
) -> None:
    """Serialize *obj* as JSON and publish it atomically with a final newline."""
    atomic_write_text(
        path,
        json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent, sort_keys=sort_keys) + "\n",
        private=private,
    )


def atomic_update_json(
    path, update, *, default=None, ensure_ascii=False, indent=2, sort_keys=False, private=False,
    recover_invalid=False,
):
    """Lock, read, transform, and atomically replace one JSON document.

    ``update`` receives the current decoded object and returns the replacement.  Invalid
    existing JSON is deliberately not replaced unless ``recover_invalid`` opts in to the
    historical fallback behavior of a particular caller.
    """
    destination = Path(path)
    with _file_lock(destination, private=private):
        try:
            with open(destination, encoding="utf-8") as handle:
                current = json.load(handle)
        except FileNotFoundError:
            current = default
        except json.JSONDecodeError:
            if not recover_invalid:
                raise
            current = default
        replacement = update(current)
        text = json.dumps(
            replacement, ensure_ascii=ensure_ascii, indent=indent, sort_keys=sort_keys
        ) + "\n"
        _atomic_write_text_unlocked(destination, text, encoding="utf-8", private=private)
        return replacement
