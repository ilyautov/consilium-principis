"""Гард свежести тиринга: корпус несёт тир, ЗАПЕЧЁННЫЙ при сборке.

Дуга закалки аппарата (5 фиксов, 2026-06-30) приземлилась ПОСЛЕ сборки корпусов Макиавелли
(2026-06-26) и Аврелия (2026-06-29). Чанк несёт только {end, source, start, text, tier} — ни
версии кода, ни хеша. Ничто не замечало, что разметка протухла: 🔵 продолжала утверждаться по
старым правилам молча. Правка инлайн-гейта (2026-07-15) сделала это критичным — она доедет до
рва ТОЛЬКО через пересборку, а сказать об этом некому.

Штамп tiering_version в build.lock + чек в doctor = единственная точка, где стухание видно.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import apparatus, buildlock  # noqa: E402
import doctor  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _built(root, slug, sub="advisors", tiering_version="omit", lock=True):
    """Собранный советник: корпус + build.lock (как после pipeline.build)."""
    adv = os.path.join(str(root), sub, slug)
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"source": "s.txt", "tier": "P1", "text": "x"}) + "\n")
    if lock:
        d = {"built_at": "2026-06-25T00:00:00Z", "counts": {"chunks": 1}}
        if tiering_version != "omit":
            d["tiering_version"] = tiering_version
        with open(os.path.join(adv, "build", "build.lock.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
    return adv


def test_write_lock_stamps_tiering_version(tmp_path):
    adv = tmp_path / "adv"
    (adv / "sources").mkdir(parents=True)
    (adv / "build").mkdir()
    lock = buildlock.write_lock(str(adv), {}, [{"tier": "P1"}], built_at="2026-07-15T00:00:00Z")
    assert lock["tiering_version"] == apparatus.TIERING_VERSION
    on_disk = json.load(open(os.path.join(str(adv), "build", "build.lock.json"), encoding="utf-8"))
    assert on_disk["tiering_version"] == apparatus.TIERING_VERSION


def test_doctor_flags_corpus_built_before_versioning(tmp_path):
    """Лок без штампа = собран до версионирования → заведомо старее правки инлайн-гейта."""
    _built(tmp_path, "machiavelli")
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is False
    assert "machiavelli" in chk["detail"]
    assert "build-advisor" in chk["detail"], "гард обязан сказать, ЧЕМ чинить"


def test_doctor_flags_corpus_older_than_code(tmp_path):
    _built(tmp_path, "old", tiering_version=apparatus.TIERING_VERSION - 1)
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is False


def test_doctor_flags_corpus_newer_than_code(tmp_path):
    """Код откатили назад — тоже расхождение, молчать нельзя."""
    _built(tmp_path, "future", tiering_version=apparatus.TIERING_VERSION + 1)
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is False


def test_doctor_ok_when_stamp_matches(tmp_path):
    _built(tmp_path, "fresh", tiering_version=apparatus.TIERING_VERSION)
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is True
    assert "fresh" not in chk["detail"] or "✓" in chk["detail"]


def test_doctor_skips_shipped_corpus_without_build_lock(tmp_path):
    """lenses/strategist шипуется без build.lock и пересобрать его юзер НЕ может (сырья нет).
    Вечный ложный крик недопустим: замороженный артефакт стережёт gov-якорь, не этот чек."""
    _built(tmp_path, "strategist", sub="lenses", lock=False)
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is True


def test_doctor_flags_lens_that_was_built_locally(tmp_path):
    """А вот линза, собранная ЛОКАЛЬНО (есть build.lock), под юрисдикцией чека."""
    _built(tmp_path, "mylens", sub="lenses")
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is False


def test_broken_lock_is_loud_not_silent(tmp_path):
    adv = _built(tmp_path, "broken")
    with open(os.path.join(adv, "build", "build.lock.json"), "w", encoding="utf-8") as f:
        f.write("{не json")
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is False


def test_no_advisors_is_not_a_failure(tmp_path):
    chk = doctor.check_corpus_tiering(str(tmp_path))
    assert chk["ok"] is True


def test_run_doctor_includes_tiering_check():
    res = doctor.run_doctor(ROOT)
    assert any(c["name"] == "corpus-tiering" for c in res["checks"]), \
        "чек есть, но доктор его не зовёт — ровно тот класс дефекта, что мы чиним"


# --- канарейка: код тиринга не меняется молча ---

TIERING_SURFACE = ("scripts/corpusbuild/apparatus.py", "scripts/corpusbuild/clean.py")
TIERING_PIN = "248908f7f8834249"   # соответствует TIERING_VERSION = 1


def test_tiering_surface_pinned():
    """Пять фиксов аппарата приземлились, не тронув ни одной версии — потому что версии не было.
    Пин делает выбор ОСОЗНАННЫМ: тронул тиринг → либо бампни TIERING_VERSION (логика изменилась,
    корпуса надо пересобрать), либо обнови пин (косметика). Молча — больше нельзя."""
    h = hashlib.sha256()
    for rel in TIERING_SURFACE:
        with open(os.path.join(ROOT, rel), "rb") as f:
            h.update(f.read())
    actual = h.hexdigest()[:16]
    assert actual == TIERING_PIN, (
        f"код тиринга изменился ({', '.join(TIERING_SURFACE)}).\n"
        f"Логика тиров изменилась? → bump apparatus.TIERING_VERSION "
        f"(={apparatus.TIERING_VERSION}) — doctor скажет юзерам пересобрать корпус.\n"
        f"Косметика (коммент/рефактор без смены тиров)? → обнови пин: TIERING_PIN = \"{actual}\""
    )
