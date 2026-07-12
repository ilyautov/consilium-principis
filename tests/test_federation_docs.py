"""docs/FEDERATION.md существует и несёт рамку personal/attended/single-machine (снятие ToS дизайном)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, "..", "docs", "FEDERATION.md")


def test_federation_doc_exists_with_framing():
    assert os.path.exists(DOC), "docs/FEDERATION.md отсутствует"
    text = open(DOC, encoding="utf-8").read().lower()
    for needle in ("personal", "attended", "single-machine"):
        assert needle in text, "нет рамки '%s' в FEDERATION.md" % needle
    # централизованная верность и дивергенция должны быть объяснены читателю
    assert "divergence" in text or "дивергенц" in text
    assert "host_single_brain" in text or "single-brain" in text
