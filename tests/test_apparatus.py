import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import apparatus as ap


def test_split_inline_author_vs_commentary():
    segs = ap.split_inline("All warfare is based on deception. [Chang Yu says: deceive all.] Hence:")
    roles = [r for _, r in segs]
    assert roles == ["author", "commentary", "author"]
    assert segs[0][0].startswith("All warfare")
    assert "Chang Yu" in segs[1][0]


def test_split_inline_unbalanced_is_commentary():
    segs = ap.split_inline("Sun Tzu said [unterminated note about strategy")
    assert ("author" in [r for _, r in segs])
    assert segs[0][1] == "author"
    assert segs[0][0].startswith("Sun Tzu")
    assert segs[-1][1] == "commentary"


def test_split_inline_nested_is_commentary():
    segs = ap.split_inline("Body [outer [inner] still note] tail")
    assert [r for _, r in segs] == ["author", "commentary", "author"]
    assert "inner" in [t for t, r in segs if r == "commentary"][0]


def test_strip_sections_cuts_front_and_back():
    text = "Intro by translator\nblah\nI. LAYING PLANS\nSun Tzu said\nAPPENDIX\nrefs"
    body = ap.strip_sections(text, front_until="I. LAYING PLANS", back_from="APPENDIX")
    assert "Sun Tzu said" in body
    assert "Intro by translator" not in body and "refs" not in body


def test_clean_removes_brackets_and_sections():
    text = "preamble\nI. LAYING PLANS\nWar is deception. [Tu Mu: yes.]\nAPPENDIX\nx"
    out = ap.clean(text, front_until="I. LAYING PLANS", back_from="APPENDIX")
    assert "War is deception." in out
    assert "Tu Mu" not in out and "preamble" not in out and "[" not in out


def test_scan_detects_apparatus():
    text = ("An Introduction by the translator about Wellington.\n" * 6 +
            "I. LAYING PLANS\n" +
            "Sun Tzu said: war is deception. [Tu Mu says: deceive.]\n" * 5 +
            "APPENDIX\nbibliography\n")
    r = ap.scan(text)
    assert r["has_apparatus"] is True
    assert r["signals"]["front_until"] == "I. LAYING PLANS"
    assert r["signals"]["back_from"].startswith("APPENDIX")
    assert r["inline_commentary"] == "bracket"
    assert r["suggested_mode"] == "tier"
    assert r["sample_author"] and r["sample_apparatus"]


def test_scan_clean_text_no_apparatus():
    r = ap.scan("Just plain prose with no editorial apparatus at all. " * 20)
    assert r["has_apparatus"] is False
    assert r["inline_commentary"] is None


def _recs(text):
    return [(("line", i + 1), ln) for i, ln in enumerate(text.splitlines()) if ln.strip()]


def test_tier_records_body_inline_and_confident_sections():
    text = ("Intro prose\nI. PLANS\nWar is deception. [Tu Mu: yes.]\nKnow the enemy.\nAPPENDIX\nrefs")
    out = ap.tier_records(_recs(text), front_until="I. PLANS", back_from="APPENDIX",
                          front_confident=True, back_confident=True, inline="bracket")
    assert all("Intro prose" not in s["text"] and "refs" not in s["text"] for s in out)  # секции срезаны
    assert any(s["tier"] == "P1" and "War is deception" in s["text"] for s in out)        # автор 🔵
    assert any(s["tier"] == "S1" and "Tu Mu" in s["text"] for s in out)                   # коммент 🟢


def test_tier_records_uncertain_front_margin_is_green_not_blue():
    text = "Mystery preamble line\nI. PLANS\nWar is deception."
    out = ap.tier_records(_recs(text), front_until="I. PLANS", back_from=None,
                          front_confident=False, back_confident=False, inline="bracket")
    pre = [s for s in out if "Mystery preamble" in s["text"]]
    assert pre and pre[0]["tier"] == "S1"            # неуверенно → 🟢, не 🔵


def test_tier_records_multiline_bracket_and_footnote_def():
    # многострочный коммент [..\n..\n..] целиком 🟢 (не только строки со скобками);
    # строка-определение сноски '[1] ...' целиком 🟢.
    body = [
        "1. Sun Tzu said: war is vital.",            # автор 🔵
        "[Ts’ao Kung opens a long note here",        # 🟢 (открыл скобку)
        "Wellington at Waterloo concealed his moves", # 🟢 (внутри скобки, своих скобок нет)
        "and deceived friend and foe alike.]",       # 🟢 (закрыл скобку)
        "2. All warfare is based on deception.",     # автор 🔵
        "[1] \"Words on Wellington,\" by Sir W. Fraser.",  # 🟢 (сноска-определение)
    ]
    recs = [(("line", i), t) for i, t in enumerate(body)]
    out = ap.tier_records(recs, inline="bracket")
    blue = " ".join(t["text"] for t in out if t["tier"] == "P1")
    green = " ".join(t["text"] for t in out if t["tier"] == "S1")
    assert "Sun Tzu said" in blue and "based on deception" in blue
    assert "Wellington" not in blue and "Ts’ao Kung" not in blue
    assert "Words on Wellington" not in blue            # сноска-определение не 🔵
    assert "Wellington" in green and "Words on Wellington" in green


import json
import pytest


def _make_advisor(tmp_path, body, manifest):
    sd = tmp_path / "sources"
    sd.mkdir(parents=True)
    (sd / "book.txt").write_text(body, encoding="utf-8")
    (sd / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return str(tmp_path)


def test_pipeline_tier_mode_tags_author_blue_commentary_green(tmp_path):
    from corpusbuild import pipeline
    body = "Intro\nI. PLANS\nWar is deception. [Tu Mu: yes.]\nAPPENDIX\nrefs\n"
    man = {"book.txt": {"tier": "P1", "apparatus": {
        "mode": "tier", "inline_commentary": "bracket",
        "front_until": "I. PLANS", "back_from": "APPENDIX",
        "front_confident": True, "back_confident": True}}}
    adv = _make_advisor(tmp_path, body, man)
    chunks = pipeline.build(adv)
    tiers = {c["tier"] for c in chunks}
    blob = " ".join(c["text"] for c in chunks)
    assert "P1" in tiers and "S1" in tiers
    assert "Tu Mu" not in " ".join(c["text"] for c in chunks if c["tier"] == "P1")
    assert "Intro" not in blob and "refs" not in blob


def test_validate_manifest_checks_apparatus():
    import manifest_builder as mb
    import tempfile, os as _os
    with tempfile.TemporaryDirectory() as sd:
        with open(_os.path.join(sd, "book.txt"), "w", encoding="utf-8") as f:
            f.write("I. PLANS\nbody\n")
        bad = {"book.txt": {"tier": "P1", "apparatus": {"mode": "nonsense"}}}
        r = mb.validate_manifest(bad, sd)
        assert not r["ok"] and any("apparatus-mode" in p["issue"] for p in r["problems"])
        # маркер границы, которого нет в тексте, ловится
        bad2 = {"book.txt": {"tier": "P1", "apparatus": {"mode": "tier", "front_until": "MISSING"}}}
        r2 = mb.validate_manifest(bad2, sd)
        assert not r2["ok"] and any(p.get("marker") == "MISSING" for p in r2["problems"])
        ok = {"book.txt": {"tier": "P1", "apparatus": {"mode": "tier", "front_until": "I. PLANS"}}}
        assert mb.validate_manifest(ok, sd)["ok"]


@pytest.mark.skipif(not os.environ.get("RUN_NET_TESTS"),
                    reason="сетевой тест Gutenberg — включи RUN_NET_TESTS=1")
def test_real_sun_tzu_tier_demotes_commentary(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import collect_common as cc, collect_pd
    from corpusbuild import pipeline
    raw = collect_pd.strip_gutenberg(cc.fetch("https://www.gutenberg.org/cache/epub/132/pg132.txt"))
    r = ap.scan(raw)
    assert r["has_apparatus"] and r["inline_commentary"] == "bracket"
    sd = tmp_path / "sources"; sd.mkdir(parents=True)
    (sd / "aow.txt").write_text(raw, encoding="utf-8")
    man = {"aow.txt": {"tier": "P1", "apparatus": {
        "mode": "tier", "inline_commentary": "bracket",
        "front_until": r["signals"]["front_until"], "back_from": r["signals"]["back_from"],
        "front_confident": r["signals"]["front_confident"],
        "back_confident": r["signals"]["back_confident"]}}}
    (sd / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    chunks = pipeline.build(str(tmp_path))
    blue = [c for c in chunks if c["tier"] == "P1"]
    green = [c for c in chunks if c["tier"] == "S1"]
    blue_text = " ".join(c["text"] for c in blue)
    green_text = " ".join(c["text"] for c in green)
    assert "Wellington" not in blue_text                       # вступление вне 🔵
    assert "Tu Mu" not in blue_text and "Ts’ao Kung" not in blue_text   # комментаторы НЕ в 🔵
    assert "Tu Mu" in green_text or "Ts’ao Kung" in green_text          # они демонтированы в 🟢
    assert "vital importance" in blue_text                     # реальный стих Сунь-Цзы → 🔵


def test_scan_toc_aware_picks_real_heading_not_contents():
    # Мини-репро реального бага Сунь-Цзы: блок 'Contents' с пунктом 'Chapter I' И реальный
    # заголовок 'Chapter I' ниже; внутренняя 'Bibliography' вступления стоит ДО тела.
    text = "\n".join([
        "THE ART OF WAR",          # 0
        "",                        # 1
        "Contents",                # 2
        "",                        # 3
        "  Introduction",          # 4
        "  Bibliography",          # 5
        "  Chapter I. Laying Plans",   # 6  (пункт оглавления)
        "  Chapter II. Waging War",    # 7
        "",                        # 8
        "",                        # 9  (2+ пустые → конец оглавления)
        "Introduction",            # 10
        "",                        # 11
        "This is the translator's essay about the author and his era.",  # 12
        "It cites [the commentator] Tu Mu more than once.",              # 13
        "",                        # 14
        "Bibliography",            # 15 (библиография вступления, ДО тела)
        "",                        # 16
        "A list of old treatises cited in the introduction.",            # 17
        "",                        # 18
        "",                        # 19
        "Chapter I. LAYING PLANS", # 20 (РЕАЛЬНЫЙ заголовок)
        "",                        # 21
        "1. Sun Tzu said: The art of war is of vital importance.",       # 22
        "2. It is a matter of life and death.",                          # 23
    ])
    r = ap.scan(text)
    assert r["signals"]["front_until"] and "Laying" in r["signals"]["front_until"]
    assert r["signals"]["back_from"] is None          # back-якорь ДО тела отвергнут
    recs = [(("line", i), ln) for i, ln in enumerate(text.split("\n"))]
    tiered = ap.tier_records(recs, front_until=r["signals"]["front_until"],
                             back_from=r["signals"]["back_from"],
                             front_confident=r["signals"]["front_confident"],
                             back_confident=r["signals"]["back_confident"])
    blue = " ".join(t["text"] for t in tiered if t["tier"] == "P1")
    assert "Sun Tzu said" in blue                     # слова автора → 🔵
    assert "translator's essay" not in blue           # вступление НЕ 🔵
    assert "list of old treatises" not in blue        # библиография вступления НЕ 🔵
