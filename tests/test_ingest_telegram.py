"""Ингест Telegram → корпус Принцепса. Парсер тестируется на моке (сеть не нужна)."""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from ingest_telegram import parse_telegram_html, posts_to_records, write_corpus

MOCK = """
<html><body>
<div class="tgme_widget_message_text js-message_text" dir="auto">Первый пост про
<b>стратегию</b> &amp; рынок<br/>вторая строка</div>
<div class="tgme_widget_message_text js-message_text" dir="auto">Второй пост &#128512; с эмодзи</div>
<div class="tgme_widget_message_text" dir="auto">x</div>
</body></html>
"""


def test_parses_posts_strips_tags_decodes_entities():
    posts = parse_telegram_html(MOCK)
    assert len(posts) == 2                       # короткий 'x' (<12) отсечён
    assert "стратегию & рынок" in posts[0]       # теги сняты, &amp;→&
    assert "вторая строка" in posts[0]           # <br/> → перенос
    assert "\n" in posts[0]
    assert "😀" in posts[1]                       # &#128512; раскрыт


def test_records_are_p1_with_source():
    recs = posts_to_records(parse_telegram_html(MOCK), "@my_channel")
    assert all(r["tier"] == "P1" for r in recs)  # твои слова = P1 твоей персоны
    assert all(r["source"] == "telegram:my_channel" for r in recs)


def test_write_corpus_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "sub", "telegram.jsonl")
        recs = posts_to_records(parse_telegram_html(MOCK), "ch")
        n = write_corpus(recs, out)
        assert n == 2
        lines = [json.loads(l) for l in open(out, encoding="utf-8")]
        assert lines[0]["tier"] == "P1" and lines[0]["source"] == "telegram:ch"


def test_empty_html_yields_nothing():
    assert parse_telegram_html("<html><body>no messages</body></html>") == []
