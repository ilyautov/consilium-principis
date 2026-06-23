import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/ — engine это пакет
from engine.lexical import LexicalEngine
from engine import Passage


def _mk(tmp, *sentences):
    adv = os.path.join(tmp, "adv")
    os.makedirs(adv, exist_ok=True)
    with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for s in sentences:
            f.write(json.dumps({"source": "src", "text": s}, ensure_ascii=False) + "\n")
    return adv


def test_retrieve_ranks_overlap_first():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, "retire into thyself and be at rest.",
                     "the most compendious way is according to nature.")
        hits = LexicalEngine().retrieve("retire into thyself", adv, top_k=2)
        assert isinstance(hits[0], Passage)
        assert "retire into thyself" in hits[0].text.lower()
        assert hits[0].score >= hits[1].score

def test_build_index_is_noop():
    assert LexicalEngine().build_index("/tmp/whatever") == {}

def test_fidelity_works_on_floor():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, "teach them better or bear with them.")
        r = LexicalEngine().fidelity_check("bear with them", adv)
        assert r.verbatim is True and r.status == "🔵"

def test_empty_question_returns_empty():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, "retire into thyself and be at rest.")
        assert LexicalEngine().retrieve("   ", adv) == []
        assert LexicalEngine().retrieve("", adv) == []

def test_retrieve_no_corpus_returns_empty():
    with tempfile.TemporaryDirectory() as t:
        assert LexicalEngine().retrieve("anything", os.path.join(t, "nope")) == []

def test_null_text_chunk_does_not_crash():
    with tempfile.TemporaryDirectory() as t:
        adv = os.path.join(t, "adv"); os.makedirs(adv)
        with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"source": "s", "text": None}) + "\n")
            f.write(json.dumps({"source": "s", "text": "retire into thyself now."}) + "\n")
        hits = LexicalEngine().retrieve("retire into thyself", adv, top_k=1)
        assert hits and "retire into thyself" in hits[0].text.lower()
