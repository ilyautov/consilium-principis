import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import chunk

def test_chunk_carries_tier_and_source():
    tagged = [{"loc": ("line", 1), "text": "a" * 200, "tier": "P1"},
              {"loc": ("line", 2), "text": "b" * 200, "tier": "P1"}]
    chunks = chunk.chunk_records(tagged, "src.txt", {"target": 300, "overlap": 50})
    assert chunks[0]["source"] == "src.txt"
    assert chunks[0]["tier"] == "P1"
    assert "start" in chunks[0] and "end" in chunks[0]

def test_chunk_does_not_merge_across_tiers():
    tagged = [{"loc": ("line", 1), "text": "intro " * 30, "tier": "B"},
              {"loc": ("line", 2), "text": "body " * 30, "tier": "P1"}]
    chunks = chunk.chunk_records(tagged, "src.txt", {"target": 1000, "overlap": 0})
    tiers = {c["tier"] for c in chunks}
    assert tiers == {"B", "P1"}  # граница тира разорвала, не склеила в один чанк

def test_overlap_chunk_start_points_to_first_tail_record():
    # overlap-хвост охватывает строки 2-3 → start второго чанка = строка 2 (не last_loc=строка 3)
    tagged = [{"loc": ("line", 1), "text": "a" * 100, "tier": "P1"},
              {"loc": ("line", 2), "text": "b" * 100, "tier": "P1"},
              {"loc": ("line", 3), "text": "c" * 100, "tier": "P1"}]
    chunks = chunk.chunk_records(tagged, "src.txt", {"target": 250, "overlap": 120})
    assert len(chunks) == 2
    assert chunks[1]["start"] == ["line", 2]   # провенанс цитаты указывает на верную строку
    assert chunks[1]["end"] == ["line", 3]
