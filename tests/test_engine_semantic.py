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


def test_blend_sets_raw_score_to_cosine(monkeypatch):
    # M4: hybrid_alpha>0 → score = (1-a)·cos + a·lex (смесь), сырой косинус сохраняется
    # в raw_score — гейт релевантности калиброван под косинус и не должен резать смесь.
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    monkeypatch.setenv("HYBRID_ALPHA", "0.5")
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("retire into thyself", "/tmp/adv", top_k=1)
    p = hits[0]
    # «retire into thyself» == запрос → lex=1.0 → смесь 0.5·0.61 + 0.5·1.0 = 0.805
    assert abs(p.score - 0.805) < 1e-9
    assert p.raw_score == 0.61                       # сырой косинус tier_full

def test_pure_semantic_raw_score_none(monkeypatch):
    # alpha=0 → score и есть косинус → raw_score не нужен (None, форма прежняя).
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    monkeypatch.setenv("HYBRID_ALPHA", "0.0")
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("retire into thyself", "/tmp/adv", top_k=1)
    assert hits[0].score == 0.61
    assert hits[0].raw_score is None
