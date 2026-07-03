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
