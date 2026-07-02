"""§1.3 moat-v2: детект языкового мисматча запрос↔корпус.

Дыра UX: «запрос давай на языке корпуса» — строчка в note; хост забыл → тихая деградация
всего пайплайна (обе честные суппрессии замера — русские вопросы против английских
пассажей). Фикс: дешёвый детерминированный детект (доля кириллицы/латиницы в query vs
язык корпуса из манифеста, иначе — вывод по сэмплу чанков) → retrieve/cite несут
`language_mismatch: true` + явную директиву «переведи запрос и повтори». БЕЗ
автоперевода (перевод — ризонинг хоста). Смешанный/пустой запрос → без флага.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pytest
import lang_check


# ── script_of: скрипт-эвристика ──

def test_script_of_detects_cyrillic_and_latin():
    assert lang_check.script_of("Как удержать власть в новом княжестве?") == "cyrillic"
    assert lang_check.script_of("How to hold power in a new principality?") == "latin"


def test_script_of_mixed_query_is_none():
    # >20% каждого скрипта → неоднозначно → не флагуем (ложные тревоги хуже)
    assert lang_check.script_of("deception обман war война мир peace") is None


def test_script_of_empty_and_symbols_are_none():
    assert lang_check.script_of("") is None
    assert lang_check.script_of(None) is None
    assert lang_check.script_of("123 !!! ??? 42") is None


def test_script_of_tolerates_minority_foreign_words():
    # пара латинских слов в русском запросе (имя, термин) — всё ещё кириллица
    assert lang_check.script_of(
        "Что Макиавелли писал про virtù и фортуну в контексте удержания власти?") == "cyrillic"


# ── corpus_script: язык корпуса (манифест → сэмпл чанков) ──

def _mk_advisor(root, slug, text, lang=None):
    d = os.path.join(root, "advisors", slug)
    os.makedirs(os.path.join(d, "sources"), exist_ok=True)
    with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"text": text, "tier": "P1", "source": "s"}, ensure_ascii=False) + "\n")
    if lang:
        json.dump({"src.txt": {"tier": "P1", "lang": lang}},
                  open(os.path.join(d, "sources", "manifest.json"), "w", encoding="utf-8"))
    return d


def test_corpus_script_from_manifest_lang(tmp_path):
    en = _mk_advisor(str(tmp_path), "en-adv", "text irrelevant when manifest has lang", lang="en")
    ru = _mk_advisor(str(tmp_path), "ru-adv", "неважно", lang="ru")
    assert lang_check.corpus_script(en) == "latin"
    assert lang_check.corpus_script(ru) == "cyrillic"


def test_corpus_script_inferred_from_chunks_without_manifest(tmp_path):
    d = _mk_advisor(str(tmp_path), "no-manifest",
                    "All warfare is based on deception, and the wise general knows it.")
    assert lang_check.corpus_script(d) == "latin"


def test_corpus_script_missing_corpus_is_none(tmp_path):
    assert lang_check.corpus_script(str(tmp_path / "ghost")) is None


# ── mismatch: сшивка ──

def test_mismatch_russian_query_english_corpus(tmp_path):
    d = _mk_advisor(str(tmp_path), "sage", "The art of war teaches deception.", lang="en")
    r = lang_check.mismatch("Как побеждать без сражения?", d)
    assert r["language_mismatch"] is True
    assert "ЯЗЫКЕ КОРПУСА" in r["language_directive"] and "en" in r["language_directive"]
    assert "перевед" in r["language_directive"].lower()      # директива: переведи и повтори


def test_mismatch_clean_cases(tmp_path):
    d = _mk_advisor(str(tmp_path), "sage2", "The art of war teaches deception.", lang="en")
    assert lang_check.mismatch("How to win without fighting?", d) is None   # совпадает
    assert lang_check.mismatch("deception обман war война мир peace", d) is None  # смешанный
    assert lang_check.mismatch("", d) is None                               # пустой — без падения
    assert lang_check.mismatch("Как побеждать?", str(tmp_path / "ghost")) is None  # нет корпуса


# ── интеграция: retrieve/cite несут флаг+директиву ──

@pytest.fixture()
def board(tmp_path, monkeypatch):
    import mcp_server
    _mk_advisor(str(tmp_path), "sage",
                "All warfare is based on deception; the supreme art is to subdue the enemy.",
                lang="en")
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    return str(tmp_path)


def test_retrieve_flags_language_mismatch(board):
    from mcp_server import dispatch
    r = dispatch("retrieve", {"query": "Как обмануть противника на войне?",
                              "advisor_dir": "advisors/sage"})
    assert r["language_mismatch"] is True
    assert "ЯЗЫКЕ КОРПУСА" in r["language_directive"]


def test_retrieve_clean_on_matching_language(board):
    from mcp_server import dispatch
    r = dispatch("retrieve", {"query": "deception in war", "advisor_dir": "advisors/sage"})
    assert "language_mismatch" not in r and "language_directive" not in r


def test_cite_flags_language_mismatch_even_when_empty(board):
    from mcp_server import dispatch
    r = dispatch("cite", {"advisor_dir": "advisors/sage", "query": "Как обмануть противника?",
                          "use_kernels": False})
    assert r["language_mismatch"] is True and "ЯЗЫКЕ КОРПУСА" in r["language_directive"]


def test_cite_clean_on_matching_language(board):
    from mcp_server import dispatch
    r = dispatch("cite", {"advisor_dir": "advisors/sage", "query": "deception in war",
                          "use_kernels": False})
    assert "language_mismatch" not in r


def test_cite_multiquery_uses_primary_for_detection(board):
    from mcp_server import dispatch
    r = dispatch("cite", {"advisor_dir": "advisors/sage",
                          "query": ["Как обмануть противника?", "deception in war"],
                          "use_kernels": False})
    assert r["language_mismatch"] is True              # primary (первый) — русский
