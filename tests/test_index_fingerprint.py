"""Гард свежести семантического индекса (data/embeddings_<name>).

Дыра (ревью 2026-07-18): индекс строился с метой {"model", "passages"}, а retrieve делал
staleness-проверку ТОЛЬКО по существованию файлов. Пересборка корпуса / смена EMBED_MODEL /
смена TIER_CHUNK_CHARS молча оставляли устаревшую матрицу — ретрив искал по векторам корпуса,
которого больше нет, `source`/цитаты могли указывать на несуществующие чанки.

Фикс (зеркало load_calibration): мета несёт fingerprint {corpus_sha256, embed_model,
chunk_chars, index_version}; retrieve сверяет и при рассинхроне fail-closed кидает
StaleIndexError. safe_retrieve ловит и деградирует semantic→lexical (наблюдаемо), НЕ падает.

Эмбеддинг МОКАЕТСЯ — реальный ollama не нужен (оффлайн-инвариант). Мирроринг test_index_tier.
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
pytest.importorskip("numpy")   # H8: tier_full тянет numpy транзитивно; нет numpy → SKIP, не collection-error
import tier_full  # noqa: E402
import engine  # noqa: E402


def _fake_embed(texts):
    """Детерминированные ненулевые векторы (нормируются вызывающим) — сеть не нужна."""
    return [[float((len(t) % 7) + 1), 1.0, 2.0] for t in texts]


def _mk_advisor(tmp_path, text="Power rests on appearances and reputation. " * 6):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    _write_corpus(str(adv), text)
    return str(adv)


def _write_corpus(adv, text):
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"source": "p.txt", "tier": "P1", "text": text},
                           ensure_ascii=False) + "\n")
    engine._CORPUS_SHA_CACHE.clear()  # сброс кэша хэша — файл переписан


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Индекс пишем в tmp (не в реальный data/); эмбеддинг мокнут; кэши чистые."""
    monkeypatch.setattr(tier_full, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(tier_full, "embed_batch", _fake_embed)
    engine._CORPUS_SHA_CACHE.clear()
    engine.reset_engine_cache()
    yield
    engine._CORPUS_SHA_CACHE.clear()
    engine.reset_engine_cache()


def test_build_index_writes_fingerprint_with_four_fields(tmp_path):
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    _, meta_path = tier_full._paths(adv)
    meta = json.load(open(meta_path, encoding="utf-8"))
    fp = meta.get("fingerprint")
    assert isinstance(fp, dict)
    assert set(fp) == {"corpus_sha256", "embed_model", "chunk_chars", "index_version"}
    assert fp["corpus_sha256"] == engine.corpus_sha256(adv)
    assert fp["embed_model"] == tier_full.EMBED_MODEL
    assert fp["chunk_chars"] == int(os.getenv("TIER_CHUNK_CHARS", "500"))


def test_retrieve_fresh_index_uses_it_without_rebuild(tmp_path, monkeypatch):
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    calls = {"n": 0}
    real_build = tier_full.build_index
    monkeypatch.setattr(tier_full, "build_index",
                        lambda d: (calls.__setitem__("n", calls["n"] + 1), real_build(d))[1])
    hits = tier_full.retrieve("how is power held", adv, top_k=3)
    assert hits and "text" in hits[0]
    assert calls["n"] == 0, "свежий индекс не должен пересобираться"


def test_stale_corpus_raises_stale_index_error(tmp_path):
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    _write_corpus(adv, "A completely different corpus about war, deception and strategy. " * 6)
    with pytest.raises(engine.StaleIndexError):
        tier_full.retrieve("how is power held", adv, top_k=3)


def test_stale_embed_model_raises(tmp_path, monkeypatch):
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    monkeypatch.setattr(tier_full, "EMBED_MODEL", "some-other-embedder")
    with pytest.raises(engine.StaleIndexError):
        tier_full.retrieve("how is power held", adv, top_k=3)


def test_stale_chunk_chars_raises(tmp_path, monkeypatch):
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    monkeypatch.setenv("TIER_CHUNK_CHARS", "137")  # ≠ дефолт 500, которым строили
    with pytest.raises(engine.StaleIndexError):
        tier_full.retrieve("how is power held", adv, top_k=3)


def test_legacy_meta_without_fingerprint_is_stale(tmp_path):
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    _, meta_path = tier_full._paths(adv)
    meta = json.load(open(meta_path, encoding="utf-8"))
    meta.pop("fingerprint", None)  # легаси-мета, как до фикса
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False)
    with pytest.raises(engine.StaleIndexError):
        tier_full.retrieve("how is power held", adv, top_k=3)


def test_pipeline_build_invalidates_stale_index(tmp_path, monkeypatch):
    """После пересборки корпуса устаревший .npy/.meta удаляются → следующий retrieve
    пересоберёт с нуля (ветка «файлов нет»), рассинхрон структурно невозможен."""
    from corpusbuild import pipeline
    adv = tmp_path / "advisors" / "sage"
    (adv / "sources").mkdir(parents=True)
    (adv / "sources" / "x.txt").write_text("Real corpus body about virtue and reason.\n",
                                            encoding="utf-8")
    emb_path, meta_path = tier_full._paths(str(adv))
    open(emb_path, "w").write("stale")           # симулируем оставшийся старый индекс
    open(meta_path, "w").write("{}")
    pipeline.build(str(adv))
    assert not os.path.isfile(emb_path) and not os.path.isfile(meta_path)


def test_doctor_semantic_index_check(tmp_path):
    """check_semantic_index: свежий fingerprint → fresh; рассинхрон → УСТАРЕЛ (виден, ok=True:
    контур цел, деградация авто); нет индекса → пропуск. Индекс лежит в <root>/data/."""
    import doctor
    adv = tmp_path / "advisors" / "sage"
    (adv / "build").mkdir(parents=True)
    _write_corpus(str(adv), "Virtue is the only good, reason the guide. " * 6)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    meta_path = data_dir / "embeddings_sage.meta.json"

    # нет индекса → пропуск, ok=True
    chk = doctor.check_semantic_index(str(tmp_path))
    assert chk["ok"] is True

    # свежий fingerprint → не в списке устаревших
    json.dump({"fingerprint": tier_full._index_fingerprint(str(adv)), "passages": []},
              open(meta_path, "w", encoding="utf-8"))
    chk = doctor.check_semantic_index(str(tmp_path))
    assert chk["ok"] is True and "устар" not in chk["detail"].lower()

    # рассинхрон (чужой corpus_sha256) → помечен УСТАРЕЛ, но doctor не роняется
    json.dump({"fingerprint": {"corpus_sha256": "deadbeef", "embed_model": "x",
                               "chunk_chars": 500, "index_version": 1}, "passages": []},
              open(meta_path, "w", encoding="utf-8"))
    chk = doctor.check_semantic_index(str(tmp_path))
    assert chk["ok"] is True
    assert "sage" in chk["detail"] and "устар" in chk["detail"].lower()


def test_run_doctor_includes_semantic_index_check():
    import doctor
    res = doctor.run_doctor(os.path.join(os.path.dirname(__file__), ".."))
    assert any(c["name"] == "semantic-index" for c in res["checks"])


def test_safe_retrieve_degrades_to_lexical_on_stale(tmp_path, monkeypatch):
    """Интеграция: StaleIndexError → safe_retrieve деградирует semantic→lexical, НЕ падает."""
    from engine.semantic import SemanticEngine
    adv = _mk_advisor(tmp_path)
    tier_full.build_index(adv)
    _write_corpus(adv, "Winning without fighting is the acme of skill in strategy. " * 6)
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    engine.reset_engine_cache()
    assert engine.resolve_engine(adv).name == "semantic"  # предусловие: выбран semantic
    res = engine.safe_retrieve("what is the acme of skill", adv, top_k=3)
    assert isinstance(res, list)                            # never crash
    assert engine.resolve_engine(adv).name == "lexical"    # деградировал наблюдаемо
