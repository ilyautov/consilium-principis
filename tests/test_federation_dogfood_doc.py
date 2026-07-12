"""Гард: догфуд-чеклист существует и несёт northstar-гейт (диверсити эмпирически проверяется до мержа)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, "..", "docs", "dev", "federation-dogfood-checklist.md")


def test_dogfood_checklist_exists_with_gate():
    assert os.path.exists(DOC), "чеклист отсутствует"
    t = open(DOC, encoding="utf-8").read().lower()
    for needle in ("federation_open", "federation_claim", "federation_submit", "federation_assemble"):
        assert needle in t, "нет шага %s" % needle
    # northstar-гейт: должен требовать РАЗНЫЕ модели и проверку реального разнообразия
    assert "worker_model" in t
    assert "diverg" in t or "разнообраз" in t or "дивергенц" in t
    # честная рамка: рассуждение облачное, не офлайн
    assert "attended" in t or "personal" in t
