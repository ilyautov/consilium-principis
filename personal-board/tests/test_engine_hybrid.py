import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/


def _fake_tf():
    m = types.ModuleType("tier_full")
    m.available = lambda: True
    m.build_index = lambda adv: None
    # семантика ставит «compendious» выше, но якорь запроса дословно в «retire» пассаже
    m.retrieve = lambda q, adv, top_k=3, rerank=False: [
        {"text": "the most compendious way is according to nature", "score": 0.58, "source": "s"},
        {"text": "retire into thyself and be at rest", "score": 0.55, "source": "s"},
    ][:top_k]
    return m


def test_hybrid_lifts_lexical_anchor(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tf())
    monkeypatch.setenv("HYBRID_ALPHA", "0.5")
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("retire into thyself", "/tmp/adv", top_k=2)
    assert "retire into thyself" in hits[0].text  # гибрид поднял точный пассаж

def test_pure_semantic_when_alpha_zero(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tf())
    monkeypatch.setenv("HYBRID_ALPHA", "0.0")
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("retire into thyself", "/tmp/adv", top_k=2)
    assert "compendious" in hits[0].text  # alpha=0 → порядок tier_full сохранён
