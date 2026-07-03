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

GUT = "https://www.gutenberg.org/cache/epub/2680/pg2680.txt"
PD_RAW = ("*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + ("Мысль. " * 50) +
          "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n")

def _catalog_root():
    import tempfile
    root = tempfile.mkdtemp()
    _write_catalog(root, [{"id": "marcus-aurelius", "name": "Марк Аврелий", "seat": "стоик",
        "source": {"platform": "gutenberg", "ref": "2680", "edition": "Long 1862",
                   "url": GUT, "pd_basis": "PG (US-PD)"}}])
    return root

def test_preview_source_by_id_uses_injected_fetch():
    root = _catalog_root()
    pv = catalog.preview_source("marcus-aurelius", root=root, fetch=lambda url, **k: PD_RAW)
    assert pv["kind"] == "pd_preview" and pv["figure"] == "Марк Аврелий"

def test_add_from_catalog_verifies_sig_and_builds():
    root = _catalog_root()
    expected_sha = catalog.text_sha256(catalog.strip_for_signature(PD_RAW))
    data = catalog.load_catalog(root); data["figures"][0]["source"]["expected"] = {"sha256": expected_sha}
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    built = {}
    res = catalog.add_from_catalog("marcus-aurelius", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW,
                                   build=lambda adv_dir, **k: built.setdefault("dir", adv_dir))
    assert res["ok"] and res["advisor"].endswith("marcus-aurelius")
    assert built["dir"].endswith("marcus-aurelius")

def test_add_from_catalog_failclosed_on_signature_drift():
    root = _catalog_root()
    data = catalog.load_catalog(root); data["figures"][0]["source"]["expected"] = {"sha256": "deadbeef"}
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    res = catalog.add_from_catalog("marcus-aurelius", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW, build=lambda *a, **k: None)
    assert not res["ok"] and "подпись" in res["error"].lower()

def test_add_nonpd_url_requires_license():
    root = _catalog_root()
    res = catalog.add_from_catalog("http://randomsite.example/book.txt", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW, build=lambda *a, **k: None)
    assert not res["ok"] and "license" in res["error"].lower()

# --- адверсариальное ревью (FIX 1-7) ---

def test_add_from_catalog_rejects_traversal_id():
    # FIX 1: id="../../evil" не должен вырваться из advisors/ в трекаемое пространство
    import tempfile
    root = tempfile.mkdtemp()
    _write_catalog(root, [{"id": "../../evil", "name": "Evil", "seat": "x",
        "source": {"platform": "gutenberg", "ref": "0", "edition": "e",
                   "url": GUT, "pd_basis": "PG (US-PD)"}}])
    built = {}
    res = catalog.add_from_catalog("../../evil", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW,
                                   build=lambda adv_dir, **k: built.setdefault("dir", adv_dir))
    assert not res["ok"]
    assert "id" in res["error"].lower() or "traversal" in res["error"].lower()
    assert "dir" not in built  # build не вызван
    # ничего не записано вне advisors/
    escaped = os.path.realpath(os.path.join(root, "advisors", "..", "..", "evil"))
    assert not os.path.exists(escaped)

def test_validate_catalog_rejects_unsafe_id():
    # FIX 2
    bad = {"version": 1, "figures": [
        {"id": "../x", "name": "X", "source": {"platform": "gutenberg", "url": "http://x"}}]}
    errs = catalog.validate_catalog(bad)
    assert any("небезопасный id" in e for e in errs)

def test_search_gutenberg_null_json_no_crash():
    # FIX 3
    res = catalog.search_gutenberg("x", fetch=lambda url, **k: "null")
    assert res["ok"] is False and res["candidates"] == []

def test_search_gutenberg_list_json_no_crash():
    # FIX 3
    res = catalog.search_gutenberg("x", fetch=lambda url, **k: "[]")
    assert res["ok"] is False and res["candidates"] == []

def test_resolve_ref_malformed_source_no_crash():
    # FIX 4: фигура без source → preview_source отдаёт error-dict, не бросает
    import tempfile
    root = tempfile.mkdtemp()
    _write_catalog(root, [{"id": "broken", "name": "Broken"}])  # нет source
    pv = catalog.preview_source("broken", root=root, fetch=lambda url, **k: PD_RAW)
    assert "error" in pv and pv.get("ok") is False

def test_preview_source_ok_shape():
    # FIX 5
    root = _catalog_root()
    pv = catalog.preview_source("marcus-aurelius", root=root, fetch=lambda url, **k: PD_RAW)
    assert pv["ok"] is True and pv["kind"] == "pd_preview"
    bad = catalog.preview_source("nope", root=root, fetch=lambda url, **k: PD_RAW)
    assert bad["ok"] is False

def test_add_from_catalog_rejects_too_short_body():
    # FIX 6: короткое тело (без expected) → не собираем мусор, build не вызван
    root = _catalog_root()
    built = {}
    res = catalog.add_from_catalog("marcus-aurelius", root=root, license=None,
                                   fetch=lambda url, **k: "x" * 50,
                                   build=lambda adv_dir, **k: built.setdefault("dir", adv_dir))
    assert not res["ok"] and "короткий" in res["error"].lower()
    assert "dir" not in built

# --- финальный ревью (FIX 2): preview/add честная оффлайн-ошибка вместо краша ---

def _raising_fetch(url, **k):
    raise ConnectionError("network unreachable")

def test_preview_source_offline_error_not_crash():
    root = _catalog_root()
    pv = catalog.preview_source("marcus-aurelius", root=root, fetch=_raising_fetch)
    assert pv["ok"] is False
    assert "оффлайн" in pv["error"].lower() or "недоступ" in pv["error"].lower()

def test_add_from_catalog_offline_error_not_crash():
    root = _catalog_root()
    built = {}
    res = catalog.add_from_catalog("marcus-aurelius", root=root, license=None,
                                   fetch=_raising_fetch,
                                   build=lambda adv_dir, **k: built.setdefault("dir", adv_dir))
    assert res["ok"] is False
    assert "оффлайн" in res["error"].lower() or "недоступ" in res["error"].lower()
    assert "dir" not in built
