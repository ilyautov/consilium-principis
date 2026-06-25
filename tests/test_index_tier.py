import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import tier_full

def test_read_chunks_carries_tier(tmp_path, monkeypatch):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    rows = [{"source": "p.txt", "tier": "P1", "text": "Power is held by appearances. " * 5},
            {"source": "t.txt", "tier": "S1", "text": "Тарасов толкует это так. " * 5}]
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    passages = tier_full._read_corpus_chunks(str(adv))
    assert any(p.get("tier") == "S1" for p in passages)
    assert all("tier" in p for p in passages)
