import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import clean, ingest


def test_provenance_header_span_strips_only_our_block():
    # реальный provenance-заголовок (# SOURCE … # ------) → срезается целиком
    hdr = ["# SOURCE: http://x", "# FETCHED: 2026", "# LICENSE: PD", "# " + "-" * 60, "Body line."]
    assert ingest._provenance_header_span(hdr) == 4
    # markdown-заголовок `# Heading` первой строкой → НЕ трогаем (0)
    assert ingest._provenance_header_span(["# Введение", "текст"]) == 0
    # «# SOURCE:» без разделителя → формат чужой, не режем
    assert ingest._provenance_header_span(["# SOURCE: x", "no separator", "body"]) == 0
    assert ingest._provenance_header_span([]) == 0

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

def test_no_manifest_all_fail_closed_A(tmp_path):
    # FAIL-CLOSED: без манифеста сборка печёт A (🟡), не P1 — некурированный текст синим не станет.
    adv = str(tmp_path)
    recs = [(("line", 1), "x"), (("line", 2), "y")]
    tagged = clean.tag_regions(recs, "f.txt", adv)
    assert all(t["tier"] == "A" for t in tagged)
