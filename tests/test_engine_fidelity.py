import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/ — engine это пакет
from engine.fidelity import verbatim_in_corpus, _norm


def _mk_corpus(tmp, text):
    adv = os.path.join(tmp, "adv")
    os.makedirs(adv, exist_ok=True)
    with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"source": "src.txt", "text": text}, ensure_ascii=False) + "\n")
    return adv


def test_verbatim_hit():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk_corpus(t, "All men are made one for another: teach them better.")
        assert verbatim_in_corpus("teach them better", adv) == "src.txt"

def test_verbatim_miss():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk_corpus(t, "All men are made one for another.")
        assert verbatim_in_corpus("you have power over your mind", adv) is None

def test_norm_collapses_ws_and_punct():
    assert _norm("Teach  them,  better!") == "teach them better"


def test_no_cross_chunk_false_positive():
    # "teach them better" does NOT exist verbatim; it only appears if chunks are joined.
    import tempfile, os, json
    with tempfile.TemporaryDirectory() as t:
        adv = os.path.join(t, "adv"); os.makedirs(adv)
        with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"source": "a", "text": "she will teach them"}) + "\n")
            f.write(json.dumps({"source": "b", "text": "better ideas arise"}) + "\n")
        from engine.fidelity import verbatim_in_corpus
        assert verbatim_in_corpus("teach them better", adv) is None

def test_missing_corpus_returns_none():
    import tempfile, os
    from engine.fidelity import verbatim_in_corpus
    with tempfile.TemporaryDirectory() as t:
        assert verbatim_in_corpus("anything", os.path.join(t, "nope")) is None

def test_empty_quote_returns_none():
    import tempfile, os, json
    from engine.fidelity import verbatim_in_corpus
    with tempfile.TemporaryDirectory() as t:
        adv = os.path.join(t, "adv"); os.makedirs(adv)
        with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"source": "s", "text": "hello world"}) + "\n")
        assert verbatim_in_corpus("   ", adv) is None
