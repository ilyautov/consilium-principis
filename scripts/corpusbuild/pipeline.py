"""Оркестратор сборки: публикует corpus/lock как одну читательскую генерацию."""
import contextlib
import os, json, shutil, subprocess, tempfile, time, uuid
from file_atomic import atomic_write_text
from . import ingest, clean, chunk as chunkmod, buildlock, paths

SUPPORTED = (".txt", ".md", ".pdf", ".epub")


class GenerationChangedError(RuntimeError):
    """Another writer published while this writer was constructing a snapshot."""


def _generations_dir(advisor_dir: str) -> str:
    return os.path.join(advisor_dir, ".corpus-generations")


@contextlib.contextmanager
def _exclusive_file_lock(path: str):
    """Cross-process exclusive advisory lock for one advisor-local coordination file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a+b") as handle:
        handle.write(b"0")
        handle.flush()
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def publisher_lock(advisor_dir: str):
    """Cross-process exclusive lock covering staging and the pointer publication."""
    with _exclusive_file_lock(os.path.join(_generations_dir(advisor_dir), ".publisher.lock")):
        yield


@contextlib.contextmanager
def source_snapshot_lock(advisor_dir: str):
    """Serialize source ingestion against a build's enumerate/extract/hash snapshot."""
    with _exclusive_file_lock(os.path.join(_generations_dir(advisor_dir), ".sources.lock")):
        yield


def active_generation_dir(advisor_dir: str):
    """The completed directory selected by the single backward-compatible build pointer."""
    build = paths.build_dir(advisor_dir)
    if not os.path.isdir(build):
        return None
    target = os.path.realpath(build)
    return target if os.path.isfile(os.path.join(target, ".generation.json")) else None


def _active_token(advisor_dir: str):
    active = active_generation_dir(advisor_dir)
    if active:
        return active
    build = paths.build_dir(advisor_dir)
    return os.path.realpath(build) if os.path.isdir(build) else None


def stage_generation(advisor_dir: str):
    """Create a private copy of the active build and its compare-and-swap token."""
    root = _generations_dir(advisor_dir)
    os.makedirs(root, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".staging-", dir=root)
    token = _active_token(advisor_dir)
    if token and os.path.isdir(token):
        shutil.copytree(token, stage, dirs_exist_ok=True, symlinks=True)
    return stage, token


def discard_staging(stage: str) -> None:
    shutil.rmtree(stage, ignore_errors=True)


def _make_directory_pointer(target: str, pointer: str, *, platform_name=None) -> None:
    """Create a directory pointer, falling back to a Windows junction without symlink rights."""
    platform_name = platform_name or os.name
    try:
        relative_target = os.path.relpath(target, os.path.dirname(pointer))
        if platform_name == "nt":
            os.symlink(relative_target, pointer, target_is_directory=True)
        else:
            os.symlink(relative_target, pointer)
    except (OSError, NotImplementedError):
        if platform_name != "nt":
            raise
        # Junctions support normal ``build/corpus.jsonl`` paths and don't require the
        # SeCreateSymbolicLinkPrivilege granted to symlink creation on many Windows hosts.
        subprocess.run(["cmd", "/c", "mklink", "/J", pointer, target],
                       check=True, capture_output=True, text=True)


def publish_generation(advisor_dir: str, stage: str, expected_token) -> str:
    """Switch the one ``build`` pointer only after every staged artifact succeeded."""
    if _active_token(advisor_dir) != expected_token:
        raise GenerationChangedError("active corpus generation changed during build")
    atomic_write_text(os.path.join(stage, ".generation.json"),
                      json.dumps({"completed": True}) + "\n")
    root = _generations_dir(advisor_dir)
    final = os.path.join(root, "generation-" + uuid.uuid4().hex)
    os.replace(stage, final)
    build = paths.build_dir(advisor_dir)
    pointer = os.path.join(advisor_dir, ".build-pointer-" + uuid.uuid4().hex)
    legacy = None
    try:
        _make_directory_pointer(final, pointer)
        if os.path.isdir(build) and not os.path.islink(build):
            legacy = os.path.join(root, "legacy-" + uuid.uuid4().hex)
            os.replace(build, legacy)
        os.replace(pointer, build)
    except BaseException:
        if os.path.lexists(pointer):
            os.unlink(pointer)
        if legacy and not os.path.lexists(build):
            os.replace(legacy, build)
        shutil.rmtree(final, ignore_errors=True)
        raise
    return final


def _is_tier_mode(source: str, advisor_dir: str) -> bool:
    from engine import provenance as prov
    man = prov.load_manifest(advisor_dir) or {}
    return ((man.get(source) or {}).get("apparatus") or {}).get("mode") == "tier"


def build(advisor_dir: str, config=None, built_at: str = "unknown"):
    config = config or {}
    chunk_cfg = config.get("chunk", {})
    src_dir = os.path.join(advisor_dir, "sources")
    with source_snapshot_lock(advisor_dir):
        all_chunks = []
        for fn in sorted(os.listdir(src_dir)):
            if os.path.splitext(fn)[1].lower() not in SUPPORTED:
                continue
            recs = ingest.extract_source(os.path.join(src_dir, fn))
            if _is_tier_mode(fn, advisor_dir):       # apparatus tier → sections+inline in one pass
                tagged = clean.apparatus_tier(recs, fn, advisor_dir)
            else:
                tagged = clean.tag_regions(recs, fn, advisor_dir)
            all_chunks.extend(chunkmod.chunk_records(tagged, fn, chunk_cfg))
        corpus = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in all_chunks)
        with publisher_lock(advisor_dir):
            stage, token = stage_generation(advisor_dir)
            try:
                atomic_write_text(os.path.join(stage, "corpus.jsonl"), corpus)
                buildlock.write_lock(advisor_dir, config, all_chunks, built_at,
                                     output_path=os.path.join(stage, "build.lock.json"),
                                     register_head=False)
                for name in ("embeddings.npy", "embeddings.meta.json"):
                    stale = os.path.join(stage, name)
                    if os.path.isfile(stale):
                        os.remove(stale)
                publish_generation(advisor_dir, stage, token)
                from governance import register_head
                register_head(advisor_dir, buildlock._gov_head(all_chunks), n=len(all_chunks))
            except BaseException:
                discard_staging(stage)
                raise
    _invalidate_semantic_index(advisor_dir)
    return all_chunks  # corpus_path() теперь автоматически отдаёт build/corpus.jsonl


def _invalidate_semantic_index(advisor_dir: str) -> None:
    """После пересборки корпуса удалить устаревший семантический индекс (data/embeddings_<slug>).
    Fail-closed на явной точке (спека 2026-07-18 §1.3): следующий retrieve пересоберёт с нуля
    (ветка «файлов нет» в tier_full.retrieve) — рассинхрон структурно невозможен. Мягко: любая
    ошибка (нет numpy / нет индекса) НЕ роняет сборку корпуса."""
    try:
        import tier_full
        for pth in tier_full._legacy_paths(advisor_dir):
            if os.path.isfile(pth):
                os.remove(pth)
    except Exception:
        pass
