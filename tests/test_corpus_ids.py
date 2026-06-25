import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import ids

def test_chunk_id_is_source_and_line_span():
    rec = {"source": "the-prince.txt", "tier": "P1", "start": ["line", 469], "end": ["line", 520], "text": "x"}
    assert ids.chunk_id(rec) == "the-prince.txt:469-520"

def test_load_corpus_reads_build(tmp_path):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    rows = [{"source": "p.txt", "tier": "P1", "start": ["line", 1], "end": ["line", 9], "text": "hi"}]
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(rows[0]) + "\n")
    got = ids.load_corpus(str(adv))
    assert len(got) == 1 and got[0]["id"] == "p.txt:1-9"
