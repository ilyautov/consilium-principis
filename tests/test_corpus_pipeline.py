import os, sys, json
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import pipeline, paths
import file_atomic

def test_build_writes_tiered_corpus(tmp_path):
    adv = tmp_path / "adv"; (adv / "sources").mkdir(parents=True)
    (adv / "sources" / "work.txt").write_text(("Sentence number %d. " * 3 + "\n") % (1,2,3) * 40, encoding="utf-8")
    json.dump({"work.txt": {"tier": "P1"}}, open(adv / "sources" / "manifest.json", "w", encoding="utf-8"))
    chunks = pipeline.build(str(adv), config={"chunk": {"target": 300, "overlap": 50}}, built_at="2026-06-25T00:00:00Z")
    assert len(chunks) > 0 and all(c["tier"] == "P1" for c in chunks)
    on_disk = [json.loads(l) for l in open(paths.corpus_path(str(adv)), encoding="utf-8") if l.strip()]
    assert len(on_disk) == len(chunks)
    assert os.path.isfile(paths.lock_path(str(adv)))


def test_build_preserves_previous_corpus_when_replace_fails(tmp_path, monkeypatch):
    adv = tmp_path / "adv"
    (adv / "sources").mkdir(parents=True)
    (adv / "sources" / "work.txt").write_text("Sentence. " * 100, encoding="utf-8")
    corpus = adv / "build" / "corpus.jsonl"
    corpus.parent.mkdir()
    previous = b'{"previous": true}\n'
    corpus.write_bytes(previous)
    monkeypatch.setattr(
        file_atomic.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("boom")),
    )

    with pytest.raises(OSError, match="boom"):
        pipeline.build(str(adv), config={})

    assert corpus.read_bytes() == previous
    assert list(corpus.parent.glob("*.tmp")) == []
