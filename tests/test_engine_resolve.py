import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
import engine as eng
from engine.lexical import LexicalEngine
from engine.semantic import SemanticEngine
from engine.hybrid import HybridEngine


def _force_mode(monkeypatch, mode):
    """Герметизация: не зависеть от реального board_config.json retrieval_mode."""
    monkeypatch.setattr(eng, "load_config_value",
                        lambda key, default: mode if key == "retrieval_mode" else default)


def test_falls_to_lexical_when_semantic_unavailable(monkeypatch):
    eng.reset_engine_cache()
    _force_mode(monkeypatch, "auto")
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    e = eng.resolve_engine("/tmp/adv")
    assert isinstance(e, LexicalEngine)

def test_picks_semantic_when_available(monkeypatch):
    eng.reset_engine_cache()
    _force_mode(monkeypatch, "auto")
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    e = eng.resolve_engine("/tmp/adv")
    assert isinstance(e, SemanticEngine)

def test_picks_hybrid_when_configured(monkeypatch):
    # Левер 1: retrieval_mode=hybrid + semantic доступен → HybridEngine (semantic ∪ lexical)
    eng.reset_engine_cache()
    _force_mode(monkeypatch, "hybrid")
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    assert isinstance(eng.resolve_engine("/tmp/adv"), HybridEngine)

def test_hybrid_mode_degrades_to_lexical_on_floor(monkeypatch):
    # hybrid сконфигурён, но semantic недоступен → пол (lexical), флаг безвреден
    eng.reset_engine_cache()
    _force_mode(monkeypatch, "hybrid")
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    assert isinstance(eng.resolve_engine("/tmp/adv"), LexicalEngine)

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


def test_prefer_does_not_pollute_cache(monkeypatch):
    # M9a: транзиентный форс (eval --engine / EVAL_ENGINE) НЕ пишет в кэш advisor'а —
    # следующий вызов без prefer резолвит дефолтный движок.
    eng.reset_engine_cache()
    _force_mode(monkeypatch, "auto")
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    e = eng.resolve_engine("/tmp/adv-prefer", prefer="lexical")
    assert isinstance(e, LexicalEngine)
    assert "/tmp/adv-prefer" not in eng._ENGINE_CACHE     # форс не закэширован
    e2 = eng.resolve_engine("/tmp/adv-prefer")
    assert isinstance(e2, SemanticEngine)                 # дефолтный путь нетронут


def test_prefer_does_not_overwrite_existing_cache(monkeypatch):
    eng.reset_engine_cache()
    _force_mode(monkeypatch, "auto")
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    e1 = eng.resolve_engine("/tmp/adv-cached")
    assert isinstance(e1, SemanticEngine)
    e2 = eng.resolve_engine("/tmp/adv-cached", prefer="lexical")
    assert isinstance(e2, LexicalEngine)                  # форс работает транзиентно
    assert eng.resolve_engine("/tmp/adv-cached") is e1    # кэш не перезаписан
