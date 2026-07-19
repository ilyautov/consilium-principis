"""H9: харнесс, доказывающий главный клейм (eval.py: fidelity_eval / parse_session /
challenge_rate_eval), был без тестов. Здесь — СИНТЕТИЧЕСКИЕ входы (ноль LLM/сети): замороженные
persona.md/corpus.jsonl/сессии, детерминированные ассерты на счётчиках метрик."""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import eval as ev  # noqa: E402  (eval.py — модуль харнесса, не builtin)


def _advisor(tmp_path, corpus_text, quote_bank_md, tier="P1"):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text(
        json.dumps({"text": corpus_text, "tier": tier}) + "\n", encoding="utf-8")
    (adv / "persona.md").write_text(quote_bank_md, encoding="utf-8")
    return str(adv)


# ─────────────────────────── fidelity_eval ───────────────────────────

def test_fidelity_eval_counts_grounded_partial_violation_extrapolation(tmp_path):
    corpus = "fortune favors the bold indeed and wise men know this truth clearly"
    persona = (
        "## Quote bank\n"
        # 🔵 дословно целиком в корпусе → grounded_ok
        "- 🔵 «fortune favors the bold indeed» — src A\n"
        # 🔵 совпал только якорь (первые 8 слов), хвост не из корпуса → partial (должно быть 🟡)
        "- 🔵 «fortune favors the bold indeed and wise men plus fabricated tail words here» — src B\n"
        # 🔵 заявлено дословным, но нигде нет → VIOLATION
        "- 🔵 «completely fabricated line that appears nowhere at all» — src C\n"
        # 🟡 экстраполяция — корректно НЕ заявлена дословной, провалом не считается
        "- 🟡 «this is only my own loose reading of it» — src D\n"
    )
    adv = _advisor(tmp_path, corpus, persona)
    r = ev.fidelity_eval(adv)
    assert r["corpus_loaded"] is True
    assert r["grounded_total"] == 3            # три заявленных-дословных (🔵), 🟡 не считается
    assert r["grounded_ok"] == 1               # только первая реально verbatim
    assert len(r["partial"]) == 1              # вторая — только якорь
    assert len(r["violations"]) == 1           # третья — фабрикация атрибуции
    assert r["extrapolation"] == 1             # 🟡 корректно вне grounded


def test_fidelity_eval_corpus_missing_marks_not_loaded(tmp_path):
    adv = tmp_path / "adv"
    adv.mkdir()
    (adv / "persona.md").write_text(
        "## Quote bank\n- 🔵 «some grounded claim here without corpus»\n", encoding="utf-8")
    r = ev.fidelity_eval(str(adv))
    assert r["corpus_loaded"] is False
    assert r["grounded_total"] == 1            # заявка есть, но verbatim не проверить (нет корпуса)
    assert r["grounded_ok"] == 0


# ─────────────────────────── parse_session (C3: без synthesis) ───────────────────────────

def test_parse_session_robust_without_synthesis(tmp_path):
    """Связь с C3: сессия БЕЗ секции синтеза не должна ронять парсер."""
    sess = tmp_path / "s.md"
    sess.write_text(
        "## 1. Вопрос\nПользователь описал ситуацию.\n"
        "## 2. Мнения\nСоветник: я не согласен с тобой — это ошибка в рассуждении.\n",
        encoding="utf-8")
    r = ev.parse_session(str(sess))            # НЕ должно бросить
    assert r["challenged"] is True             # маркеры «не согласен»/«ошибк» пойманы
    assert "не согласен" in r["markers"] or "несоглас" in r["markers"]
    assert r["turn_of_flip_section"] == 2      # возражение в такте #2
    for k in ("file", "challenged", "markers", "holds_to_verdict", "collapsed"):
        assert k in r


def test_parse_session_empty_file_does_not_crash(tmp_path):
    sess = tmp_path / "empty.md"
    sess.write_text("", encoding="utf-8")
    r = ev.parse_session(str(sess))
    assert r["challenged"] is False and r["markers"] == []


def test_parse_session_pure_agreement_not_challenged(tmp_path):
    sess = tmp_path / "yes.md"
    sess.write_text("## 1. Итог\nТы прав, отличный вопрос, верное направление.\n", encoding="utf-8")
    r = ev.parse_session(str(sess))
    assert r["challenged"] is False            # ни одного challenge-маркера
    assert r["collapsed"] is True              # хвост — сплошное поддакивание


# ─────────────────────────── challenge_rate_eval ───────────────────────────

def test_challenge_rate_eval_on_synthetic_sessions(tmp_path, monkeypatch):
    challenged = tmp_path / "c.md"
    challenged.write_text("## 1.\nСоветник: ты перепутал причину и следствие — это слепое пятно.\n",
                          encoding="utf-8")
    agree = tmp_path / "a.md"
    agree.write_text("## 1.\nСогласен с тобой, ты молодец.\n", encoding="utf-8")
    # challenge_rate_eval строит sess_dir из HERE и глобит; подменяем glob на синтетику (ноль сети/FS-репо)
    monkeypatch.setattr(ev.glob, "glob", lambda pattern: [str(challenged), str(agree)])
    r = ev.challenge_rate_eval()
    assert r["total"] == 2
    assert r["challenged"] == 1                # только первая сессия реально оспорила юзера
    assert len(r["sessions"]) == 2
