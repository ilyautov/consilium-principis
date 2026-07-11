"""quote_of_day — детерминированная verbatim-цитата дня из P1/P2-корпуса. Pull-only, гарантия 🔵."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def _make_advisor(tmp_path, chunks):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return str(adv)


P1_CHUNKS = [
    {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"},
    {"text": "Waste no more time arguing about what a good man should be.", "tier": "P1",
     "source": "Meditations 10.16"},
    {"text": "The happiness of your life depends upon the quality of your thoughts.", "tier": "P2",
     "source": "Meditations 5.16"},
]


def test_returns_blue_quote_from_corpus(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, P1_CHUNKS)
    r = _quote_of_day(adv, date="2026-07-11")
    assert r["marker"] == "🔵"
    assert r["source"]
    corpus_texts = [c["text"] for c in P1_CHUNKS]
    assert r["text"] in corpus_texts          # реально из корпуса, не выдумана


def test_deterministic_same_date(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, P1_CHUNKS)
    a = _quote_of_day(adv, date="2026-07-11")
    b = _quote_of_day(adv, date="2026-07-11")
    assert a["text"] == b["text"]


def test_varies_across_dates(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, P1_CHUNKS)
    picks = {_quote_of_day(adv, date=f"2026-07-{d:02d}")["text"] for d in range(1, 20)}
    assert len(picks) >= 2                     # не всегда один и тот же чанк


def test_empty_or_non_p1_pool_no_blue(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, [
        {"text": "Some low-tier apparatus text.", "tier": "A", "source": "x"}])
    r = _quote_of_day(adv, date="2026-07-11")
    assert r.get("marker") != "🔵"
    assert "note" in r
