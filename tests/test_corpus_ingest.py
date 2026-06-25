import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import ingest

def test_reads_utf8(tmp_path):
    p = tmp_path / "a.txt"; p.write_text("Привет мир\nвторая строка\n", encoding="utf-8")
    recs = ingest.extract_source(str(p))
    assert recs[0] == (("line", 1), "Привет мир")
    assert len(recs) == 2

def test_reads_cp1251(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes("Управление по Макиавелли\n".encode("cp1251"))
    recs = ingest.extract_source(str(p))
    assert recs[0][1] == "Управление по Макиавелли"

def test_skips_blank_lines(tmp_path):
    p = tmp_path / "c.txt"; p.write_text("one\n\n\ntwo\n", encoding="utf-8")
    recs = ingest.extract_source(str(p))
    assert [r[1] for r in recs] == ["one", "two"]
