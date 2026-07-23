import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/


def _fake_tf():
    m = types.ModuleType("tier_full")
    m.available = lambda: True
    m.build_index = lambda adv: None
    # семантика ставит «compendious» выше, но якорь запроса дословно в «retire» пассаже
    m.retrieve = lambda q, adv, top_k=3: [
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


def test_hybrid_rrf_attaches_raw_cosine(monkeypatch):
    # M4: RRF-score — не косинус. Сырой косинус semantic-ноги прокидывается в raw_score,
    # чтобы гейт применял калиброванную полосу к косинусу, а не к слитому скору.
    from engine.hybrid import HybridEngine
    from engine import Passage
    eng = HybridEngine()
    sem = [Passage("shared chunk", 0.42, "s"), Passage("sem only", 0.60, "s")]
    lex = [Passage("shared chunk", 0.9, "s"), Passage("lex only", 0.8, "s")]
    monkeypatch.setattr(eng.sem, "retrieve", lambda q, a, top_k=3: sem)
    monkeypatch.setattr(eng.lex, "retrieve", lambda q, a, top_k=3: lex)
    hits = eng.retrieve("q", "/tmp/adv", top_k=3)
    by_text = {p.text: p for p in hits}
    assert by_text["shared chunk"].raw_score == 0.42   # сырой косинус, не RRF-смесь
    assert by_text["sem only"].raw_score == 0.60
    assert by_text["lex only"].raw_score is None       # lexical-only: косинуса нет → None

def test_hybrid_rrf_prefers_sem_leg_raw_over_blend(monkeypatch):
    # semantic-нога сама со смесью (hybrid_alpha>0): в fused уходит её raw (косинус),
    # а не blend-score ноги.
    from engine.hybrid import HybridEngine
    from engine import Passage
    eng = HybridEngine()
    sem = [Passage("chunk", 0.805, "s", None, raw_score=0.61)]
    lex = [Passage("chunk", 0.9, "s")]
    monkeypatch.setattr(eng.sem, "retrieve", lambda q, a, top_k=3: sem)
    monkeypatch.setattr(eng.lex, "retrieve", lambda q, a, top_k=3: lex)
    hits = eng.retrieve("q", "/tmp/adv", top_k=1)
    assert hits[0].raw_score == 0.61
