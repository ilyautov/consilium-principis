"""Контрактные тесты strip-логики сборщиков корпусов (M7): collect_pd / collect_web /
collect_transcript (+ общий collect_common.html_to_text / land_to_sources).

Без сети: синтетический вход (HTML/текст/фейковый youtube_transcript_api в sys.modules).
Контракт: Gutenberg-обёртка срезается, из HTML уходит script/style/nav и выбирается
контейнер, telegram-сообщения склеиваются, транскрипт фильтрует пустые реплики,
land_to_sources пишет provenance-заголовок + сайдкар-манифест.
"""
import json
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import collect_common as cc
import collect_pd as cpd
import collect_web as cw
import collect_transcript as ct


# ───────────────────────── collect_pd.strip_gutenberg ─────────────────────────

def test_strip_gutenberg_cuts_legal_wrapper():
    raw = ("The Project Gutenberg EBook, junk header\n"
           "*** START OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***\n"
           "\nBody first line.\nBody second line.\n\n"
           "*** END OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***\n"
           "Footer legal junk follows.")
    assert cpd.strip_gutenberg(raw) == "Body first line.\nBody second line."


def test_strip_gutenberg_without_markers_is_identity():
    assert cpd.strip_gutenberg("  plain text body  ") == "plain text body"


def test_strip_gutenberg_end_only_cuts_footer():
    raw = ("Body line stays.\n"
           "*** END OF THIS PROJECT GUTENBERG EBOOK X ***\nFooter junk.")
    assert cpd.strip_gutenberg(raw) == "Body line stays."


# ───────────────────────── collect_common.html_to_text ─────────────────────────

def test_html_to_text_drops_chrome_keeps_article():
    pytest.importorskip("bs4")
    html = ("<html><body><nav>menu junk</nav><header>hdr junk</header>"
            "<article><h1>Title</h1><p>Real content here.</p>"
            "<script>evil()</script><style>.x{}</style></article>"
            "<footer>foot junk</footer></body></html>")
    out = cc.html_to_text(html)
    assert "Real content here." in out
    assert "evil" not in out and ".x{}" not in out
    assert "menu junk" not in out and "foot junk" not in out


def test_html_to_text_selector_picks_container():
    pytest.importorskip("bs4")
    html = ("<html><body><div id='a'>First block.</div>"
            "<div id='b'>Second block.</div></body></html>")
    out = cc.html_to_text(html, selector="#b")
    assert "Second block." in out and "First block." not in out


def test_html_to_text_fallback_without_bs4(monkeypatch):
    """CI-нога без bs4: sys.modules['bs4']=None → import внутри html_to_text падает →
    stdlib-фолбэк (regex-стрип). Контракт фолбэка слабее bs4-пути: теги сняты, script/style
    вырезаны С содержимым, текст сохранён — но nav/header/footer-хром НЕ убирается."""
    monkeypatch.setitem(sys.modules, "bs4", None)   # import bs4 → ImportError
    html = ("<html><body><nav>menu junk</nav><header>hdr junk</header>"
            "<article><h1>Title</h1><p>Real content here.</p>"
            "<script>evil()</script><style>.x{}</style></article>"
            "<footer>foot junk</footer></body></html>")
    out = cc.html_to_text(html)
    assert "Real content here." in out and "Title" in out
    assert "evil" not in out and ".x{}" not in out     # script/style вырезаны с телом
    assert "<" not in out and ">" not in out           # все теги сняты
    assert "menu junk" in out                          # хром остаётся — осознанная цена фолбэка


# ───────────────────────── collect_web.extract_telegram ─────────────────────────

def test_extract_telegram_joins_message_divs():
    pytest.importorskip("bs4")
    html = ("<html><body>"
            "<div class='tgme_widget_message_text'>First post text</div>"
            "<div class='tgme_widget_message_text'>Second<br>post lines</div>"
            "<div class='tgme_widget_message_text'>   </div>"      # пустое сообщение отсекается
            "</body></html>")
    out = cw.extract_telegram(html)
    assert "First post text" in out and "Second" in out and "post lines" in out
    assert out.count("\n\n") == 1                                 # два непустых сообщения, один шов


# ───────────────────────── collect_transcript.youtube_transcript ─────────────────────────

def _fake_yt_api(items):
    mod = types.ModuleType("youtube_transcript_api")

    class YouTubeTranscriptApi:
        @staticmethod
        def get_transcript(video_id, languages=None):
            return items

    mod.YouTubeTranscriptApi = YouTubeTranscriptApi
    return mod


def test_youtube_transcript_joins_and_filters_empty():
    fake = _fake_yt_api([{"text": " Hello there "}, {"text": "  "}, {"text": "world"}, {}])
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "youtube_transcript_api", fake)
        assert ct.youtube_transcript("vid") == "Hello there\nworld"


def test_youtube_transcript_without_package_exits_honest(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)   # import → ImportError
    with pytest.raises(SystemExit) as ei:
        ct.youtube_transcript("vid")
    assert ei.value.code == 3
    assert "youtube-transcript-api" in capsys.readouterr().err


# ───────────────────────── collect_common.land_to_sources ─────────────────────────

def test_land_to_sources_writes_provenance_header_and_manifest(tmp_path):
    adv = tmp_path / "advisors" / "demo-figure"
    adv.mkdir(parents=True)
    path = cc.land_to_sources(str(adv), "My Source Name", "  body text  ",
                              url="https://example.org/x", license_note="public-domain",
                              extra_meta={"type": "essay"})
    text = open(path, encoding="utf-8").read()
    head, _, body = text.partition("# " + "-" * 60)
    assert "# SOURCE: https://example.org/x" in head
    assert "# FETCHED: " in head and "# LICENSE: public-domain" in head
    assert "# TYPE: essay" in head
    assert body.strip() == "body text"
    assert os.path.basename(path) == "my-source-name.txt"             # slugify

    manifest = os.path.join(adv, "sources", "_provenance.jsonl")
    rec = json.loads(open(manifest, encoding="utf-8").readline())
    assert rec["file"] == "my-source-name.txt" and rec["url"] == "https://example.org/x"
    assert rec["license"] == "public-domain" and rec["chars"] == len("  body text  ")
    assert rec["type"] == "essay"


def test_land_to_sources_reserves_suffix_without_overwriting(tmp_path):
    """Повторное имя сохраняет оба источника и провенанс с итоговым именем."""
    adv = tmp_path / "advisor"
    first = cc.land_to_sources(str(adv), "Book", "first", url="u1", license_note="PD")
    second = cc.land_to_sources(str(adv), "Book", "second", url="u2", license_note="PD")
    assert [os.path.basename(first), os.path.basename(second)] == ["book.txt", "book-2.txt"]
    assert open(first, encoding="utf-8").read().endswith("first\n")
    assert open(second, encoding="utf-8").read().endswith("second\n")
    rows = [json.loads(line) for line in open(adv / "sources" / "_provenance.jsonl", encoding="utf-8")]
    assert [row["file"] for row in rows] == ["book.txt", "book-2.txt"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_land_to_sources_makes_source_directory_files_and_existing_sidecar_private(tmp_path):
    """Personal source landing tightens its directory and provenance even when they predate it."""
    adv = tmp_path / "advisor"
    sources = adv / "sources"
    sources.mkdir(parents=True)
    sidecar = sources / "_provenance.jsonl"
    sidecar.write_text('{"old": true}\n', encoding="utf-8")
    os.chmod(sources, 0o755)
    os.chmod(sidecar, 0o644)

    landed = cc.land_to_sources(str(adv), "Book", "body", url="u", license_note="PD")

    assert (sources.stat().st_mode & 0o777) == 0o700
    assert (os.stat(landed).st_mode & 0o777) == 0o600
    assert (sidecar.stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_land_to_sources_never_chmods_a_collided_symlink_target(tmp_path):
    """A collision with a symlink selects a suffix without changing the symlink target's access."""
    adv = tmp_path / "advisor"
    sources = adv / "sources"
    sources.mkdir(parents=True)
    target = tmp_path / "outside-source.txt"
    target.write_text("outside\n", encoding="utf-8")
    os.chmod(target, 0o644)
    os.symlink(target, sources / "book.txt")

    landed = cc.land_to_sources(str(adv), "Book", "body", url="u", license_note="PD")

    assert os.path.basename(landed) == "book-2.txt"
    assert target.stat().st_mode & 0o777 == 0o644
