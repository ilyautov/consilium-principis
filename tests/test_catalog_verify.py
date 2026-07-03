import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import catalog

def _root_with(fig):
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "catalog"))
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "figures": [fig]}, f, ensure_ascii=False)
    return root

RAW = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nТекст произведения.\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"

def test_verify_reports_ok_when_signature_matches():
    sha = catalog.text_sha256(catalog.strip_for_signature(RAW))
    root = _root_with({"id": "m", "name": "M", "source": {"platform": "gutenberg", "url": "https://www.gutenberg.org/x",
                       "pd_basis": "PG", "expected": {"sha256": sha}}})
    rep = catalog.verify_catalog(root, fetch=lambda url, **k: RAW)
    assert rep["ok"] and rep["entries"][0]["status"] == "ok"

def test_verify_flags_drift():
    root = _root_with({"id": "m", "name": "M", "source": {"platform": "gutenberg", "url": "https://www.gutenberg.org/x",
                       "pd_basis": "PG", "expected": {"sha256": "deadbeef"}}})
    rep = catalog.verify_catalog(root, fetch=lambda url, **k: RAW)
    assert not rep["ok"] and rep["entries"][0]["status"] == "drift"

def test_seed_writes_signatures():
    root = _root_with({"id": "m", "name": "M", "source": {"platform": "gutenberg", "url": "https://www.gutenberg.org/x",
                       "pd_basis": "PG"}})
    rep = catalog.verify_catalog(root, fetch=lambda url, **k: RAW, seed=True)
    data = catalog.load_catalog(root)
    assert data["figures"][0]["source"]["expected"]["sha256"] == catalog.text_sha256(catalog.strip_for_signature(RAW))
