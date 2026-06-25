import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import clean

def _manifest(adv, data):
    os.makedirs(os.path.join(adv, "sources"), exist_ok=True)
    json.dump(data, open(os.path.join(adv, "sources", "manifest.json"), "w", encoding="utf-8"))

def test_tags_tier_per_region(tmp_path):
    adv = str(tmp_path)
    _manifest(adv, {"med.txt": {"tier": "P1", "regions": [
        {"tier": "B", "until": "THE FIRST BOOK"},
        {"tier": "P1", "from": "THE FIRST BOOK"}]}})
    recs = [(("line", 1), "intro"), (("line", 2), "THE FIRST BOOK"), (("line", 3), "real")]
    tagged = clean.tag_regions(recs, "med.txt", adv)
    assert [t["tier"] for t in tagged] == ["B", "P1", "P1"]
    assert tagged[0]["text"] == "intro" and tagged[0]["loc"] == ("line", 1)

def test_no_manifest_all_p1(tmp_path):
    adv = str(tmp_path)
    recs = [(("line", 1), "x"), (("line", 2), "y")]
    tagged = clean.tag_regions(recs, "f.txt", adv)
    assert all(t["tier"] == "P1" for t in tagged)
