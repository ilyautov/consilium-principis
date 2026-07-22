"""A corpus generation is published as one immutable reader snapshot."""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

pytest.importorskip("numpy")
from corpusbuild import buildlock, pipeline, paths
import tier_full


def _fake_embed(texts):
    return [[float((len(text) % 5) + 1), 1.0] for text in texts]


def _advisor(tmp_path):
    advisor = tmp_path / "advisor"
    (advisor / "sources").mkdir(parents=True)
    (advisor / "sources" / "book.txt").write_text("Old counsel. " * 80, encoding="utf-8")
    return advisor


@pytest.fixture(autouse=True)
def _isolated_index(tmp_path, monkeypatch):
    monkeypatch.setattr(tier_full, "DATA_DIR", str(tmp_path / "legacy-data"))
    monkeypatch.setattr(tier_full, "embed_batch", _fake_embed)


def test_failed_corpus_publication_keeps_previous_generation_and_cleans_staging(tmp_path, monkeypatch):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    old_generation = os.path.realpath(paths.build_dir(str(advisor)))
    old_corpus = open(paths.corpus_path(str(advisor)), encoding="utf-8").read()
    (advisor / "sources" / "book.txt").write_text("New counsel. " * 80, encoding="utf-8")

    monkeypatch.setattr(buildlock, "write_lock", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("lock failed")))

    with pytest.raises(OSError, match="lock failed"):
        pipeline.build(str(advisor), built_at="new")

    assert os.path.realpath(paths.build_dir(str(advisor))) == old_generation
    assert open(paths.corpus_path(str(advisor)), encoding="utf-8").read() == old_corpus
    assert not list((advisor / ".corpus-generations").glob(".staging-*"))


def test_interrupted_pointer_switch_keeps_old_generation_and_removes_unpublished_generation(tmp_path, monkeypatch):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    old_generation = os.path.realpath(paths.build_dir(str(advisor)))
    generations = advisor / ".corpus-generations"
    before = set(generations.glob("generation-*"))
    (advisor / "sources" / "book.txt").write_text("New counsel. " * 80, encoding="utf-8")

    monkeypatch.setattr(pipeline.os, "symlink", lambda *_args: (_ for _ in ()).throw(OSError("pointer failed")))
    with pytest.raises(OSError, match="pointer failed"):
        pipeline.build(str(advisor), built_at="new")

    assert os.path.realpath(paths.build_dir(str(advisor))) == old_generation
    assert set(generations.glob("generation-*")) == before
    assert not list(generations.glob(".staging-*"))


def test_failed_index_publication_keeps_previous_completed_generation(tmp_path, monkeypatch):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    tier_full.build_index(str(advisor))
    old_generation = os.path.realpath(paths.build_dir(str(advisor)))

    monkeypatch.setattr(tier_full, "embed_batch", lambda _texts: (_ for _ in ()).throw(OSError("embed failed")))
    with pytest.raises(OSError, match="embed failed"):
        tier_full.build_index(str(advisor))

    assert os.path.realpath(paths.build_dir(str(advisor))) == old_generation
    assert not list((advisor / ".corpus-generations").glob(".staging-*"))
    monkeypatch.setattr(tier_full, "embed_batch", _fake_embed)
    assert tier_full.retrieve("counsel", str(advisor))


def test_retrieve_builds_missing_index_in_a_new_complete_generation(tmp_path):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    corpus_generation = os.path.realpath(paths.build_dir(str(advisor)))

    assert tier_full.retrieve("counsel", str(advisor))
    assert os.path.realpath(paths.build_dir(str(advisor))) != corpus_generation


def test_index_build_migrates_legacy_build_to_the_single_generation_pointer(tmp_path):
    advisor = _advisor(tmp_path)
    (advisor / "build").mkdir()
    (advisor / "build" / "corpus.jsonl").write_text(
        json.dumps({"source": "book.txt", "tier": "P1", "text": "Legacy counsel. " * 40}) + "\n",
        encoding="utf-8",
    )

    tier_full.build_index(str(advisor))

    assert os.path.islink(paths.build_dir(str(advisor)))
    assert os.path.isfile(os.path.join(os.path.realpath(paths.build_dir(str(advisor))), "embeddings.npy"))


def test_reader_uses_old_complete_generation_while_new_index_is_staged(tmp_path, monkeypatch):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    tier_full.build_index(str(advisor))
    old_generation = os.path.realpath(paths.build_dir(str(advisor)))
    started = threading.Event()
    release = threading.Event()
    worker_ident = []

    def slow_embed(texts):
        if threading.get_ident() in worker_ident:
            started.set()
            assert release.wait(timeout=5)
        return _fake_embed(texts)

    monkeypatch.setattr(tier_full, "embed_batch", slow_embed)
    def rebuild():
        worker_ident.append(threading.get_ident())
        tier_full.build_index(str(advisor))

    worker = threading.Thread(target=rebuild)
    worker.start()
    assert started.wait(timeout=5)

    # A reader that starts during the rebuild still observes the old, complete snapshot.
    assert tier_full.retrieve("counsel", str(advisor))
    assert os.path.realpath(paths.build_dir(str(advisor))) == old_generation

    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert os.path.realpath(paths.build_dir(str(advisor))) != old_generation
    # Open readers retain a valid old generation after the pointer moves.
    assert os.path.isfile(os.path.join(old_generation, "corpus.jsonl"))
    assert os.path.isfile(os.path.join(old_generation, "embeddings.npy"))


def test_competing_index_and_corpus_publishers_both_commit_in_order(tmp_path, monkeypatch):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    started = threading.Event()
    release = threading.Event()
    errors = []

    def slow_embed(texts):
        started.set()
        assert release.wait(timeout=5)
        return _fake_embed(texts)

    monkeypatch.setattr(tier_full, "embed_batch", slow_embed)
    indexer = threading.Thread(target=lambda: _run(lambda: tier_full.build_index(str(advisor)), errors))
    indexer.start()
    assert started.wait(timeout=5)
    (advisor / "sources" / "book.txt").write_text("New counsel. " * 80, encoding="utf-8")
    builder = threading.Thread(target=lambda: _run(
        lambda: pipeline.build(str(advisor), built_at="new"), errors))
    builder.start()

    release.set()
    indexer.join(timeout=5)
    builder.join(timeout=5)
    assert not indexer.is_alive() and not builder.is_alive()
    assert errors == []
    lock = json.load(open(os.path.join(paths.build_dir(str(advisor)), "build.lock.json"), encoding="utf-8"))
    assert lock["built_at"] == "new"
    assert "New counsel" in open(paths.corpus_path(str(advisor)), encoding="utf-8").read()


def test_windows_pointer_falls_back_to_non_privileged_junction(tmp_path, monkeypatch):
    target = tmp_path / "generation"
    pointer = tmp_path / "build-pointer"
    target.mkdir()
    calls = []

    monkeypatch.setattr(pipeline.os, "symlink", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("privilege")))
    monkeypatch.setattr(pipeline.subprocess, "run",
                        lambda args, **kwargs: calls.append((args, kwargs)))

    pipeline._make_directory_pointer(str(target), str(pointer), platform_name="nt")

    assert calls == [(["cmd", "/c", "mklink", "/J", str(pointer), str(target)],
                      {"check": True, "capture_output": True, "text": True})]


def test_completed_directory_pointer_is_recognised_without_symlink_metadata(tmp_path):
    advisor = tmp_path / "advisor"
    build = advisor / "build"
    build.mkdir(parents=True)
    (build / ".generation.json").write_text('{"completed": true}\n', encoding="utf-8")

    assert pipeline.active_generation_dir(str(advisor)) == os.path.realpath(build)


def test_snapshot_fingerprint_remains_valid_after_pointer_moves(tmp_path):
    advisor = _advisor(tmp_path)
    pipeline.build(str(advisor), built_at="old")
    tier_full.build_index(str(advisor))
    corpus_file, _emb, meta_file = tier_full._reader_snapshot(str(advisor))
    meta = json.load(open(meta_file, encoding="utf-8"))
    (advisor / "sources" / "book.txt").write_text("New counsel. " * 80, encoding="utf-8")
    pipeline.build(str(advisor), built_at="new")

    assert tier_full._fingerprint_matches(meta, str(advisor), corpus_file=corpus_file)


def test_ingest_waits_for_build_source_snapshot_and_cannot_split_lock_from_corpus(tmp_path, monkeypatch):
    import collect_common

    advisor = _advisor(tmp_path)
    started = threading.Event()
    release = threading.Event()
    build_errors = []
    ingest_done = threading.Event()
    original_extract = pipeline.ingest.extract_source

    def blocked_extract(path):
        started.set()
        assert release.wait(timeout=5)
        return original_extract(path)

    monkeypatch.setattr(pipeline.ingest, "extract_source", blocked_extract)
    builder = threading.Thread(target=lambda: _run(
        lambda: pipeline.build(str(advisor), built_at="snapshot"), build_errors))
    builder.start()
    assert started.wait(timeout=5)

    def land_source():
        collect_common.land_to_sources(str(advisor), "added", "Added while build runs.",
                                      url="https://example.test/added", license_note="test")
        ingest_done.set()

    ingester = threading.Thread(target=land_source)
    ingester.start()
    try:
        assert not ingest_done.wait(timeout=0.2)
    finally:
        release.set()
    builder.join(timeout=5)
    ingester.join(timeout=5)
    assert not builder.is_alive() and not ingester.is_alive()
    assert build_errors == []

    lock = json.load(open(os.path.join(paths.build_dir(str(advisor)), "build.lock.json"), encoding="utf-8"))
    corpus = [json.loads(line) for line in open(paths.corpus_path(str(advisor)), encoding="utf-8")]
    assert set(lock["sources"]) == {"book.txt"}
    assert {chunk["source"] for chunk in corpus} == {"book.txt"}
    assert (advisor / "sources" / "added.txt").is_file()


@pytest.mark.skipif(os.name != "nt", reason="requires a real NTFS junction")
def test_windows_junction_fallback_publishes_two_generations_and_retrieves(tmp_path, monkeypatch):
    advisor = _advisor(tmp_path)
    monkeypatch.setattr(pipeline.os, "symlink",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no symlink privilege")))
    monkeypatch.setattr(tier_full, "embed_batch", _fake_embed)

    pipeline.build(str(advisor), built_at="first")
    (advisor / "sources" / "book.txt").write_text("Second generation counsel. " * 80,
                                                     encoding="utf-8")
    pipeline.build(str(advisor), built_at="second")

    assert os.path.isdir(paths.build_dir(str(advisor)))
    assert not os.path.islink(paths.build_dir(str(advisor)))
    assert "Second generation" in open(paths.corpus_path(str(advisor)), encoding="utf-8").read()
    assert tier_full.retrieve("counsel", str(advisor))


def _run(operation, errors):
    try:
        operation()
    except BaseException as exc:  # test reports publication failures from worker threads
        errors.append(exc)
