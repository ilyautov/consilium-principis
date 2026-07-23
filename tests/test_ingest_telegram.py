"""Ингест Telegram → корпус Принцепса. Парсер тестируется на моке (сеть не нужна)."""
import os, sys, json, tempfile
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import ingest_telegram
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


def test_write_corpus_collision_preserves_existing_file_and_uses_suffix(tmp_path):
    """The final writer reserves a new filename instead of truncating a raced destination."""
    out = tmp_path / "telegram.jsonl"
    out.write_text('{"old": true}\n', encoding="utf-8")
    recs = posts_to_records(parse_telegram_html(MOCK), "ch")
    assert write_corpus(recs, str(out)) == 2
    assert out.read_text(encoding="utf-8") == '{"old": true}\n'
    assert (tmp_path / "telegram-2.jsonl").exists()


def test_standalone_default_ingest_preserves_existing_telegram_corpus(tmp_path, monkeypatch):
    """CLI/default ingest never silently overwrites telegram.jsonl already on disk."""
    corpus = tmp_path / "principis_corpus"
    corpus.mkdir()
    original = corpus / "telegram.jsonl"
    original.write_text('{"old": true}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ingest_telegram, "_fetch_channel_html_canonical", lambda _handle: MOCK)
    result = ingest_telegram.ingest("@my_channel")
    assert original.read_text(encoding="utf-8") == '{"old": true}\n'
    assert result["out"] == os.path.join("principis_corpus", "telegram-2.jsonl")
    assert (corpus / "telegram-2.jsonl").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_default_ingest_preserves_and_tightens_existing_telegram_corpus(tmp_path, monkeypatch):
    """The default collision flow does not overwrite private history and locks both files down."""
    corpus = tmp_path / "principis_corpus"
    corpus.mkdir()
    original = corpus / "telegram.jsonl"
    original.write_text('{"old": true}\n', encoding="utf-8")
    os.chmod(corpus, 0o755)
    os.chmod(original, 0o644)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ingest_telegram, "_fetch_channel_html_canonical", lambda _handle: MOCK)

    result = ingest_telegram.ingest("@my_channel")
    created = corpus / "telegram-2.jsonl"

    assert original.read_text(encoding="utf-8") == '{"old": true}\n'
    assert result["out"] == os.path.join("principis_corpus", "telegram-2.jsonl")
    assert (corpus.stat().st_mode & 0o777) == 0o700
    assert (original.stat().st_mode & 0o777) == 0o600
    assert (created.stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_bare_explicit_output_does_not_change_the_working_directory_mode(tmp_path, monkeypatch):
    """A caller-owned CWD is not a Telegram corpus directory and must not be tightened."""
    os.chmod(tmp_path, 0o755)
    monkeypatch.chdir(tmp_path)

    write_corpus(posts_to_records(parse_telegram_html(MOCK), "ch"), "telegram.jsonl")

    assert (tmp_path.stat().st_mode & 0o777) == 0o755
    assert (tmp_path / "telegram.jsonl").stat().st_mode & 0o777 == 0o600


def test_empty_html_yields_nothing():
    assert parse_telegram_html("<html><body>no messages</body></html>") == []


def test_ingest_canonicalizes_handle_before_fetch_and_corpus_metadata(monkeypatch):
    """CR/LF из входного handle не доходит ни до URL-fetch, ни до source в JSONL."""
    seen = []

    def fake_fetch(handle):
        seen.append(handle)
        return MOCK

    monkeypatch.setattr(ingest_telegram, "_fetch_channel_html_canonical", fake_fetch)
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "telegram.jsonl")
        result = ingest_telegram.ingest("@my_channel\r\nforged: metadata", out)
        records = [json.loads(line) for line in open(out, encoding="utf-8")]

    canonical = "my_channelforgedmetadata"
    assert seen == [canonical]
    assert result["handle"] == canonical
    assert {record["source"] for record in records} == {f"telegram:{canonical}"}
    assert all("\r" not in record["source"] and "\n" not in record["source"]
               for record in records)


def test_ingest_canonicalizes_handle_once(monkeypatch):
    """Один канонический handle переиспользуется и для fetch, и для corpus."""
    original = ingest_telegram._safe_handle
    calls = []

    def tracking_safe_handle(handle):
        calls.append(handle)
        return original(handle)

    import collect_common
    monkeypatch.setattr(ingest_telegram, "_safe_handle", tracking_safe_handle)
    monkeypatch.setattr(collect_common, "fetch", lambda *args, **kwargs: MOCK)
    with tempfile.TemporaryDirectory() as t:
        ingest_telegram.ingest("@my_channel", os.path.join(t, "telegram.jsonl"))

    assert calls == ["@my_channel"]
