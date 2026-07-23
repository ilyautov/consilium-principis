"""Офлайн-тест citation-rate eval (ALCE-style). Детерминировано, без сети/ollama.

Гейт (_fidelity_check) — единственный источник правды, переиспользован как есть, не мокается.
Фикстура-корпус построена по паттерну tests/test_fidelity_tiers.py (build/corpus.jsonl, tier).
Спека: внутренний дизайн-док (citation rate eval).
"""
import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "experiments"))
import pytest  # noqa: E402
import citation_rate_eval as E  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
KNOWN_TEXT = "it is safer to be feared than loved when one of the two must be lacking"


@pytest.fixture(autouse=True)
def _clamp_root_at_tmp(monkeypatch, tmp_path):
    """H5 read-гард в mcp_server._fidelity_check клампит advisor_dir корнем; синтетический
    корпус score_claims строит под tmp_path (adv=str(tmp_path)) → наводим _root на tmp_path,
    иначе гейт честно отвергает abs-путь как вне корня и всё уходит в 🟡."""
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))


def _mk_corpus(adv):
    """Как в tests/test_fidelity_tiers.py: build/corpus.jsonl с явным tier."""
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"source": "prince.txt", "tier": "P1", "text": KNOWN_TEXT}, ensure_ascii=False) + "\n")


def test_load_battery_has_in_and_out_of_corpus():
    rows = E.load_battery()
    assert len(rows) >= 6
    coverages = {r["coverage"] for r in rows}
    assert coverages == {"in_corpus", "out_of_corpus"}
    for r in rows:
        assert r["id"] and r["question"]


def test_score_claims_precision_fabrication_abstention(tmp_path):
    adv = str(tmp_path)
    _mk_corpus(adv)
    claims = [
        # (a) настоящая дословная цитата, заявлена как verbatim → должна верифицироваться
        {"advisor_dir": adv, "quote": "safer to be feared than loved", "purported_verbatim": True},
        # (b) выдуманная цитата, заявлена как verbatim → НЕ должна верифицироваться (фабрикация)
        {"advisor_dir": adv, "quote": "Макиавелли обожал мороженое по средам", "purported_verbatim": True},
        # (c) цитата вне корпуса, честно НЕ заявлена как verbatim → гейт должен вернуть 🟡 (воздержание корректно)
        {"advisor_dir": adv, "quote": "совершенно неизвестная фраза из другой книги вообще", "purported_verbatim": False},
    ]
    result = E.score_claims(claims)

    assert result["n_claims"] == 3
    assert result["n_purported_verbatim"] == 2
    assert result["n_verified"] == 1
    assert result["citation_precision"] == 0.5
    assert result["fabrication_rate"] == 0.5

    assert result["n_purported_fabricated_or_out"] == 1
    assert result["n_abstained_correct"] == 1
    assert result["abstention_correct"] == 1.0

    scored_by_quote = {s["quote"]: s for s in result["scored"]}
    assert scored_by_quote["safer to be feared than loved"]["status"] == "🔵"
    assert scored_by_quote["safer to be feared than loved"]["verified"] is True
    assert scored_by_quote["Макиавелли обожал мороженое по средам"]["status"] == "🟡"
    assert scored_by_quote["Макиавелли обожал мороженое по средам"]["verified"] is False
    assert scored_by_quote["совершенно неизвестная фраза из другой книги вообще"]["status"] == "🟡"


def test_score_claims_empty_purported_true_precision_is_none(tmp_path):
    adv = str(tmp_path)
    _mk_corpus(adv)
    claims = [{"advisor_dir": adv, "quote": "что-то вне корпуса совсем", "purported_verbatim": False}]
    result = E.score_claims(claims)
    assert result["citation_precision"] is None
    assert result["fabrication_rate"] is None
    assert result["abstention_correct"] == 1.0


def test_score_claims_empty_purported_false_abstention_is_none(tmp_path):
    adv = str(tmp_path)
    _mk_corpus(adv)
    claims = [{"advisor_dir": adv, "quote": "safer to be feared than loved", "purported_verbatim": True}]
    result = E.score_claims(claims)
    assert result["abstention_correct"] is None
    assert result["citation_precision"] == 1.0


def test_score_claims_deterministic_ci(tmp_path):
    adv = str(tmp_path)
    _mk_corpus(adv)
    claims = [
        {"advisor_dir": adv, "quote": "safer to be feared than loved", "purported_verbatim": True},
        {"advisor_dir": adv, "quote": "полностью выдуманная цитата номер один", "purported_verbatim": True},
        {"advisor_dir": adv, "quote": "полностью выдуманная цитата номер два", "purported_verbatim": True},
    ]
    r1 = E.score_claims(claims)
    r2 = E.score_claims(claims)
    assert r1["precision_ci"] == r2["precision_ci"]
    assert r1["precision_ci"] is not None


def test_extract_quote_claims_pulls_guillemet_and_straight_quotes(tmp_path):
    adv = str(tmp_path)
    text = 'Как писал Макиавелли: «safer to be feared than loved». Также говорят "another quoted phrase here".'
    claims = E.extract_quote_claims(text, adv)
    quotes = {c["quote"] for c in claims}
    assert "safer to be feared than loved" in quotes
    assert "another quoted phrase here" in quotes
    assert all(c["purported_verbatim"] is True for c in claims)
    assert all(c["advisor_dir"] == adv for c in claims)


def test_extract_quote_claims_none_and_empty_safe():
    assert E.extract_quote_claims(None, "adv") == []
    assert E.extract_quote_claims("", "adv") == []
    assert E.extract_quote_claims("нет кавычек тут вообще", "adv") == []


def test_format_table_mentions_key_metrics(tmp_path):
    adv = str(tmp_path)
    _mk_corpus(adv)
    claims = [
        {"advisor_dir": adv, "quote": "safer to be feared than loved", "purported_verbatim": True},
        {"advisor_dir": adv, "quote": "совсем другая выдуманная штука", "purported_verbatim": False},
    ]
    council = E.score_claims(claims)
    bare = E.score_claims(claims)
    result = {"council": council, "bare_baseline": bare, "question_abstention_rate": 1.0, "n_questions": 8}
    txt = E.format_table(result)
    assert "precision" in txt.lower() or "точност" in txt.lower()
    assert "fabrication" in txt.lower() or "фабрикац" in txt.lower()


def test_write_results_roundtrip(tmp_path):
    result = {"council": {"citation_precision": 1.0}, "bare_baseline": {"citation_precision": 0.4},
              "question_abstention_rate": 1.0, "n_questions": 8}
    path = os.path.join(str(tmp_path), "out.json")
    E.write_results(result, path)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["result"]["council"]["citation_precision"] == 1.0
    assert payload["seed"] == E.SEED


def test_main_run_without_key_fails_honestly(capsys, monkeypatch):
    monkeypatch.setattr(E, "_api_available", lambda: False)
    rc = E.main(["--run"])
    assert rc == 1
    out = capsys.readouterr().out.lower()
    assert "ключ" in out or "openrouter" in out


def test_main_no_args_prints_help_and_exits_zero(capsys):
    rc = E.main([])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "usage" in out or "--run" in out


def test_smoke_run_as_script_prints_help_and_exits_zero():
    env = dict(os.environ, OLLAMA_HOST="http://127.0.0.1:59999")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "experiments", "citation_rate_eval.py")],
        capture_output=True, text=True, env=env, cwd=ROOT,
    )
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower() or "--run" in proc.stdout.lower()
