import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import catalog

def _write_catalog(root, figures):
    os.makedirs(os.path.join(root, "catalog"), exist_ok=True)
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "figures": figures}, f, ensure_ascii=False)

def test_load_and_validate_good_catalog():
    with tempfile.TemporaryDirectory() as root:
        _write_catalog(root, [{
            "id": "marcus-aurelius", "name": "Марк Аврелий", "seat": "стоик",
            "lang": "en",
            "source": {"platform": "gutenberg", "ref": "2680",
                       "edition": "пер. George Long, 1862",
                       "url": "https://www.gutenberg.org/cache/epub/2680/pg2680.txt",
                       "pd_basis": "Project Gutenberg (US-PD)"}}])
        data = catalog.load_catalog(root)
        assert catalog.validate_catalog(data) == []
        assert catalog.get_figure(data, "marcus-aurelius")["name"] == "Марк Аврелий"
        assert catalog.get_figure(data, "nope") is None

def test_validate_rejects_bad_entries():
    bad = {"version": 1, "figures": [
        {"id": "x"},
        {"id": "y", "name": "Y", "source": {"platform": "randomsite", "url": "http://x"}},
    ]}
    errs = catalog.validate_catalog(bad)
    assert any("source" in e for e in errs)
    assert any("платформа" in e for e in errs)

def test_load_missing_catalog_is_empty_failclosed():
    with tempfile.TemporaryDirectory() as root:
        data = catalog.load_catalog(root)
        assert data == {"version": 1, "figures": []}

def test_strip_and_signature_deterministic():
    raw = ("*** START OF THE PROJECT GUTENBERG EBOOK X ***\n"
           "Настоящий текст произведения.\n"
           "*** END OF THE PROJECT GUTENBERG EBOOK X ***\n")
    stripped = catalog.strip_for_signature(raw)
    assert "PROJECT GUTENBERG" not in stripped
    assert "Настоящий текст" in stripped
    sha = catalog.text_sha256(stripped)
    assert sha == catalog.text_sha256(catalog.strip_for_signature(raw))

def test_verify_signature_failclosed_on_drift():
    stripped = "abc"
    ok, actual, _ = catalog.verify_signature(stripped, {"sha256": catalog.text_sha256("abc")})
    assert ok
    ok2, _, reason = catalog.verify_signature(stripped, {"sha256": "deadbeef"})
    assert not ok2 and "подпись" in reason.lower()

def test_verify_signature_absent_expected_warns_not_fails():
    ok, actual, reason = catalog.verify_signature("abc", None)
    assert ok and "не посеяна" in reason.lower()

def test_build_preview_shape_and_ocr_warn():
    raw = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + ("Ясный текст. " * 40) + \
          "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    pv = catalog.build_preview(name="Марк Аврелий", edition="Long 1862",
                               pd_basis="PG (US-PD)", url="https://www.gutenberg.org/x", raw=raw)
    assert pv["kind"] == "pd_preview"
    assert pv["figure"] == "Марк Аврелий" and pv["pd_basis"] == "PG (US-PD)"
    assert "PROJECT GUTENBERG" not in pv["sample"]
    assert pv["bytes"] > 0 and len(pv["sha256"]) == 64
    assert pv["pd_host_ok"] is True
    assert pv["warnings"] == []

def test_build_preview_flags_ocr_noise_and_nonpd_host():
    noisy = "@#$%^&*<>|~`" * 60 + " a"
    pv = catalog.build_preview(name="X", edition="e", pd_basis="?",
                               url="http://randomsite.example/x", raw=noisy)
    assert pv["pd_host_ok"] is False
    assert any("шум" in w.lower() or "качество" in w.lower() for w in pv["warnings"])
