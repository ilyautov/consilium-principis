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
