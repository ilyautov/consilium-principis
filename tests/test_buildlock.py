import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import buildlock

def test_lock_records_hashes_and_counts(tmp_path):
    adv = tmp_path / "adv"; (adv / "sources").mkdir(parents=True); (adv / "build").mkdir()
    (adv / "sources" / "a.txt").write_text("hello", encoding="utf-8")
    chunks = [{"tier": "P1"}, {"tier": "P1"}, {"tier": "S1"}]
    lock = buildlock.write_lock(str(adv), {"chunk": {"target": 900}}, chunks, built_at="2026-06-25T00:00:00Z")
    assert lock["counts"] == {"P1": 2, "S1": 1, "chunks": 3}
    assert "a.txt" in lock["sources"] and lock["sources"]["a.txt"].startswith("sha256:")
    on_disk = json.load(open(os.path.join(str(adv), "build", "build.lock.json"), encoding="utf-8"))
    assert on_disk["built_at"] == "2026-06-25T00:00:00Z"
