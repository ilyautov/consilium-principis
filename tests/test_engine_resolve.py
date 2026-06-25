import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
import engine as eng
from engine.lexical import LexicalEngine
from engine.semantic import SemanticEngine


def test_falls_to_lexical_when_semantic_unavailable(monkeypatch):
    eng.reset_engine_cache()
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    e = eng.resolve_engine("/tmp/adv")
    assert isinstance(e, LexicalEngine)

def test_picks_semantic_when_available(monkeypatch):
    eng.reset_engine_cache()
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    e = eng.resolve_engine("/tmp/adv")
    assert isinstance(e, SemanticEngine)

def test_runtime_failure_degrades_and_invalidates(monkeypatch):
    eng.reset_engine_cache()
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    def boom(*a, **k):
        raise ConnectionError("ollama died")
    monkeypatch.setattr(SemanticEngine, "retrieve", boom)
    # safe_retrieve должен поймать падение и пере-резолвить вниз
    hits = eng.safe_retrieve("q", "/tmp/adv")  # корпуса нет → lexical вернёт []
    assert hits == []
    assert isinstance(eng.resolve_engine("/tmp/adv"), LexicalEngine)  # кэш инвалидирован вниз
