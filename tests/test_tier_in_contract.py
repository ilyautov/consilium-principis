"""Тир доезжает до потребителя через контракт Engine (слой 1 правки #2).

Дефект: тир ЛЕЖИТ в индексе у каждого пассажа (data/embeddings_<slug>.meta.json;
machiavelli P1 3791 / S1 1924 / B 154) и умирает на выдаче — tier_full.retrieve собирает
{text,score,source} из passages[i], выбрасывая passages[i]["tier"], а датакласс Passage
поля не имеет. Итог: cite решает про 🔵 по пулу, о составе которого ничего не знает,
а диагностика вынуждена лезть в meta.json в обход контракта.

Слой 1 НИЧЕГО не решает про ранжирование и не трогает ров — только делает тир видимым.
Политика (квота/бонус/пулы) — отдельное решение после замера; литература (Airbnb KDD'20)
прямо предупреждает, что офлайн-нейтральность не доказывает безвредность квоты.

tier=None означает «тир неизвестен», НЕ «первоисточник»: потребитель обязан трактовать
None fail-closed, иначе поле стало бы дырой вместо гарда.
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from engine import Passage  # noqa: E402


# --- контракт ---

def test_passage_carries_tier_defaulting_to_none():
    p = Passage(text="t", score=0.1, source="s")
    assert p.tier is None, "дефолт None = «тир неизвестен», трактуется fail-closed"
    assert Passage(text="t", score=0.1, source="s", tier="P1").tier == "P1"


def test_positional_construction_still_works():
    """Обратная совместимость: 12 мест зовут Passage позиционно 3 аргументами."""
    p = Passage("t", 0.2, "s")
    assert (p.text, p.score, p.source, p.tier) == ("t", 0.2, "s", None)


# --- tier_full.retrieve: точка, где тир умирал ---

def _index(tmp_path, monkeypatch, passages):
    import numpy as np
    import tier_full
    emb = str(tmp_path / "e.npy")
    meta = str(tmp_path / "e.meta.json")
    np.save(emb, np.eye(len(passages), 4, dtype="float32"))
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"passages": passages}, f, ensure_ascii=False)
    monkeypatch.setattr(tier_full, "_paths", lambda adv: (emb, meta))
    monkeypatch.setattr(tier_full, "_embed_query",
                        lambda q: np.array([1.0, 0.0, 0.0, 0.0], dtype="float32"))
    return tier_full


def test_tier_full_retrieve_carries_tier(tmp_path, monkeypatch):
    tf = _index(tmp_path, monkeypatch, [
        {"text": "everyone sees what you appear to be", "source": "prince.txt", "tier": "P1"},
        {"text": "Тарасов толкует это так", "source": "tarasov.txt", "tier": "S1"},
    ])
    hits = tf.retrieve("appearances", "/tmp/adv", top_k=2)
    assert all("tier" in h for h in hits), "retrieve выбрасывает тир, который есть в индексе"
    assert hits[0]["tier"] == "P1"


def test_tier_full_retrieve_tier_none_when_index_lacks_it(tmp_path, monkeypatch):
    """Легаси-индекс без поля → None (неизвестно), а не выдуманный P1."""
    tf = _index(tmp_path, monkeypatch, [{"text": "old", "source": "x.txt"}])
    assert tf.retrieve("q", "/tmp/adv", top_k=1)[0]["tier"] is None


# --- semantic ---

def _fake_tier_full(rows):
    m = types.ModuleType("tier_full")
    m.available = lambda: True
    m.build_index = lambda adv: None
    m.retrieve = lambda q, adv, top_k=3, rerank=False: rows[:top_k]
    return m


_ROWS = [{"text": "retire into thyself", "score": 0.61, "source": "long.txt", "tier": "P1"},
         {"text": "комментарий", "score": 0.55, "source": "sec.txt", "tier": "S1"}]


def test_semantic_propagates_tier(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full(_ROWS))
    monkeypatch.delenv("HYBRID_ALPHA", raising=False)
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("где покой?", "/tmp/adv", top_k=2)
    assert [h.tier for h in hits] == ["P1", "S1"]


def test_semantic_propagates_tier_through_hybrid_rescoring(monkeypatch):
    """Ветка alpha>0 пересобирает Passage — тир обязан выжить и там."""
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full(_ROWS))
    monkeypatch.setenv("HYBRID_ALPHA", "0.5")
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("retire thyself", "/tmp/adv", top_k=2)
    assert {h.tier for h in hits} == {"P1", "S1"}
    assert all(h.tier is not None for h in hits)


# --- lexical (пол без ollama) ---

def _corpus(tmp_path, rows):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(adv)


def test_lexical_carries_tier_from_corpus(tmp_path):
    from engine.lexical import LexicalEngine
    adv = _corpus(tmp_path, [
        {"source": "p.txt", "tier": "P1", "text": "Power is held by appearances alone."},
        {"source": "t.txt", "tier": "S1", "text": "Тарасов толкует власть иначе совсем."},
    ])
    hits = LexicalEngine().retrieve("appearances power", adv, top_k=2)
    assert hits and all(h.tier is not None for h in hits), "лексический пол теряет тир"
    assert hits[0].tier == "P1"


def test_lexical_tier_none_when_corpus_lacks_it(tmp_path):
    from engine.lexical import LexicalEngine
    adv = _corpus(tmp_path, [{"source": "x.txt", "text": "Power is held by appearances alone."}])
    assert LexicalEngine().retrieve("appearances", adv, top_k=1)[0].tier is None


# --- rrf (гибридное слияние пересобирает Passage) ---

def test_rrf_preserves_tier():
    from engine.rrf import rrf_fuse
    a = [Passage("alpha text", 0.9, "p.txt", "P1")]
    b = [Passage("beta text", 0.8, "t.txt", "S1")]
    fused = rrf_fuse([a, b], top_k=2)
    by_text = {p.text: p.tier for p in fused}
    assert by_text["alpha text"] == "P1" and by_text["beta text"] == "S1", \
        "RRF пересобирает Passage и роняет тир"


# --- eval.retrieve: граница, через которую ходит cite ---

def test_eval_retrieve_exposes_tier(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full(_ROWS))
    monkeypatch.delenv("HYBRID_ALPHA", raising=False)
    monkeypatch.setenv("EVAL_ENGINE", "semantic")
    import eval as _eval
    hits = _eval.retrieve("где покой?", "/tmp/adv", top_k=2)
    assert all("tier" in h for h in hits), "eval.retrieve — та граница, где cite теряет тир"
    assert hits[0]["tier"] == "P1"


def test_eval_lexical_fallback_exposes_tier(tmp_path):
    """Деградация на лексический пол не должна ослеплять потребителя по тиру."""
    import eval as _eval
    adv = _corpus(tmp_path, [
        {"source": "p.txt", "tier": "P1", "text": "Power is held by appearances alone."},
    ])
    hits = _eval.lexical_retrieve("appearances power", adv, top_k=1)
    assert hits and hits[0]["tier"] == "P1"
