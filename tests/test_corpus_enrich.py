import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import enrich
import pytest

def test_enrichment_record_is_derived_never_quote():
    r = enrich.make_enrichment_record("пример", "текст", derived_from=["p:1-2"])
    assert r["tier"] == "derived" and r["never_quote"] is True
    assert r["kind"] == "пример" and r["derived_from"] == ["p:1-2"]

def test_cross_domain_requires_kernel_trace():
    # L2.3.2: кросс-домен ВСЕГДА должен трассироваться к кернелу
    with pytest.raises(ValueError):
        enrich.make_enrichment_record("кросс-домен", "t", derived_from=["p:1-2"], traces_to_kernel=None)
    ok = enrich.make_enrichment_record("кросс-домен", "t", derived_from=["p:1-2"], traces_to_kernel="K1")
    assert ok["traces_to_kernel"] == "K1"
