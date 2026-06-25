import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import paths

def test_corpus_path_prefers_build(tmp_path):
    adv = tmp_path / "marcus"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
    assert paths.corpus_path(str(adv)) == str(adv / "build" / "corpus.jsonl")

def test_corpus_path_falls_back_to_legacy(tmp_path):
    adv = tmp_path / "marcus"
    adv.mkdir()
    (adv / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
    assert paths.corpus_path(str(adv)) == str(adv / "corpus.jsonl")

def test_corpus_path_defaults_to_build_when_neither_exists(tmp_path):
    adv = tmp_path / "marcus"; adv.mkdir()
    assert paths.corpus_path(str(adv)) == str(adv / "build" / "corpus.jsonl")
