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
