"""§1.4 moat-v2: golden↔corpus версионирование.

Дыра: пересборка корпуса смещает чанки — якоря golden молча протухают, метрики
интерпретируются на несуществующем корпусе. Фикс: продюсеры golden пишут первой
строкой meta-запись с хэшем корпуса (sha256 corpus.jsonl, 12 hex); eval-лоадер при
мисматче громко предупреждает в stderr (НЕ падение). Легаси-файлы без meta грузятся
молча как раньше (бэк-компат). Файлы scripts/golden/ гитигнорятся — меняется ТУЛИНГ.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pytest
import golden_meta


def _mk_advisor(root, slug, text="All warfare is based on deception and timing of the wise."):
    d = os.path.join(root, "advisors", slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"text": text, "tier": "P1", "source": "s"}, ensure_ascii=False) + "\n")
    return d


# ── хэш и meta-запись ──

def test_corpus_sha12_deterministic_and_content_sensitive(tmp_path):
    a = _mk_advisor(str(tmp_path), "a")
    h1 = golden_meta.corpus_sha12(a)
    assert isinstance(h1, str) and len(h1) == 12 and int(h1, 16) >= 0
    assert golden_meta.corpus_sha12(a) == h1                     # детерминизм
    b = _mk_advisor(str(tmp_path), "b", text="different corpus content entirely here")
    assert golden_meta.corpus_sha12(b) != h1                     # содержимое-чувствителен


def test_corpus_sha12_missing_corpus_is_none(tmp_path):
    assert golden_meta.corpus_sha12(str(tmp_path / "ghost")) is None


def test_meta_record_and_split(tmp_path):
    a = _mk_advisor(str(tmp_path), "a")
    rec = golden_meta.meta_record(a)
    assert rec["_meta"]["corpus_sha12"] == golden_meta.corpus_sha12(a)
    meta, rows = golden_meta.split_meta([rec, {"q": "x", "anchor": "y"}])
    assert meta["corpus_sha12"] == rec["_meta"]["corpus_sha12"]
    assert rows == [{"q": "x", "anchor": "y"}]                   # meta не течёт в данные
    meta2, rows2 = golden_meta.split_meta([{"q": "legacy"}])     # легаси: без meta
    assert meta2 is None and rows2 == [{"q": "legacy"}]


# ── drift-предупреждение ──

def test_warn_on_drift_loud_on_mismatch(tmp_path, capsys):
    a = _mk_advisor(str(tmp_path), "a")
    drifted = golden_meta.warn_on_drift({"corpus_sha12": "deadbeef0000"}, a, path="x.jsonl")
    err = capsys.readouterr().err
    assert drifted is True
    assert "DRIFT" in err and "deadbeef0000" in err and "x.jsonl" in err


def test_warn_on_drift_silent_on_match_and_legacy(tmp_path, capsys):
    a = _mk_advisor(str(tmp_path), "a")
    assert golden_meta.warn_on_drift({"corpus_sha12": golden_meta.corpus_sha12(a)}, a) is False
    assert golden_meta.warn_on_drift(None, a) is False           # легаси-файл: молча
    assert golden_meta.warn_on_drift({}, a) is False
    assert capsys.readouterr().err == ""


# ── продюсеры пишут хэш ──

def test_gen_golden_writes_meta_header(tmp_path, monkeypatch):
    import gen_golden
    monkeypatch.chdir(tmp_path)
    long_text = ("Fortune is the arbiter of one half of our actions, but she still leaves us "
                 "to direct the other half. " * 6)
    adv = _mk_advisor(str(tmp_path), "sage", text=long_text)
    os.makedirs(str(tmp_path / "scripts" / "golden"), exist_ok=True)
    monkeypatch.setattr(gen_golden, "gen_questions",
                        lambda author, passage, model, timeout=120:
                        ("What does fortune arbitrate?", "Who controls outcomes in life?"))
    gen_golden.run("sage", k=1, model="mock")
    lines = [json.loads(l) for l in
             open(str(tmp_path / "scripts" / "golden" / "sage.auto.jsonl"), encoding="utf-8")]
    assert "_meta" in lines[0]
    assert lines[0]["_meta"]["corpus_sha12"] == golden_meta.corpus_sha12(adv)
    assert all("_meta" not in l for l in lines[1:]) and len(lines) > 1


def test_synth_write_jsonl_meta_optional(tmp_path):
    import synth_eval
    adv = _mk_advisor(str(tmp_path), "sage")
    p = str(tmp_path / "out.jsonl")
    synth_eval.write_jsonl(p, [{"q": "x"}], advisor_dir=adv)
    lines = [json.loads(l) for l in open(p, encoding="utf-8")]
    assert lines[0]["_meta"]["corpus_sha12"] == golden_meta.corpus_sha12(adv)
    assert lines[1] == {"q": "x"}
    synth_eval.write_jsonl(p, [{"q": "x"}])                      # без advisor_dir — как раньше
    lines = [json.loads(l) for l in open(p, encoding="utf-8")]
    assert lines == [{"q": "x"}]


# ── лоадер eval: warning на дрейфе, тишина на матче и легаси ──

@pytest.fixture()
def golden_env(tmp_path, monkeypatch):
    import eval as _eval
    adv = _mk_advisor(str(tmp_path), "sage")
    gdir = str(tmp_path / "golden")
    os.makedirs(gdir, exist_ok=True)
    monkeypatch.setattr(_eval, "GOLDEN_DIR", gdir)
    return _eval, adv, gdir


def _write_golden(gdir, name, rows):
    with open(os.path.join(gdir, name), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_load_golden_warns_on_corpus_drift(golden_env, capsys):
    _eval, adv, gdir = golden_env
    _write_golden(gdir, "sage.retrieval.jsonl",
                  [{"_meta": {"corpus_sha12": "deadbeef0000"}}, {"q": "x", "anchor": "y"}])
    rows, path = _eval.load_golden("sage", "retrieval", advisor_dir=adv)
    assert rows == [{"q": "x", "anchor": "y"}]                   # meta отфильтрована из данных
    assert "DRIFT" in capsys.readouterr().err


def test_load_golden_silent_on_match(golden_env, capsys):
    _eval, adv, gdir = golden_env
    _write_golden(gdir, "sage.retrieval.jsonl",
                  [{"_meta": {"corpus_sha12": golden_meta.corpus_sha12(adv)}},
                   {"q": "x", "anchor": "y"}])
    rows, _ = _eval.load_golden("sage", "retrieval", advisor_dir=adv)
    assert rows == [{"q": "x", "anchor": "y"}]
    assert "DRIFT" not in capsys.readouterr().err


def test_load_golden_legacy_without_meta_silent(golden_env, capsys):
    _eval, adv, gdir = golden_env
    _write_golden(gdir, "sage.retrieval.jsonl", [{"q": "x", "anchor": "y"}])
    rows, _ = _eval.load_golden("sage", "retrieval", advisor_dir=adv)
    assert rows == [{"q": "x", "anchor": "y"}]                   # грузится молча, как сегодня
    assert capsys.readouterr().err == ""
