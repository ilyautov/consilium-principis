import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/


def _fake_tier_full():
    m = types.ModuleType("tier_full")
    m.available = lambda: True
    m.build_index = lambda adv: None
    m.retrieve = lambda q, adv, top_k=3, rerank=False: [
        {"text": "retire into thyself", "score": 0.61, "source": "long.txt"}][:top_k]
    return m


def test_retrieve_maps_to_passages(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("где покой?", "/tmp/adv", top_k=1)
    from engine import Passage
    assert isinstance(hits[0], Passage)
    assert hits[0].score == 0.61 and hits[0].source == "long.txt"

def test_available_reflects_tier_full(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    from engine.semantic import SemanticEngine
    assert SemanticEngine.available() is True

def test_available_false_when_tier_full_missing(monkeypatch):
    # имитируем отсутствие tier_full → available() должен вернуть False, не падать
    monkeypatch.setitem(sys.modules, "tier_full", None)  # import даст ошибку → except → False
    from engine.semantic import SemanticEngine
    assert SemanticEngine.available() is False

def test_build_index_returns_chunk_chars(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    monkeypatch.setenv("TIER_CHUNK_CHARS", "500")
    from engine.semantic import SemanticEngine
    meta = SemanticEngine().build_index("/tmp/adv")
    assert meta == {"chunk_chars": 500}
