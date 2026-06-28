"""Скаффолдер+валидатор тир-манифеста — спина доверяемой сборки (там живёт ров).

Контур (🔵 = слова автора) держится на sources/manifest.json: тир P1/S1/B + region-маркеры.
Писался руками; если маркер не совпадает с текстом ДОСЛОВНО — тиры молча съезжают и 🔵 даётся
не на тех словах (реальная дыра рва). Суждение о тире — ризонинг; запись + ВАЛИДАЦИЯ (маркеры
реально есть в источнике, тиры валидны, файлы на месте) — детерминированно.
"""
import os, sys, tempfile, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from manifest_builder import scaffold_manifest, validate_manifest, VALID_TIERS


def test_scaffold_builds_expected_structure():
    m = scaffold_manifest([
        {"source": "prince.txt", "tier": "P1", "attribution": "Machiavelli", "title": "The Prince",
         "regions": [{"tier": "B", "until": "To the Magnificent"}, {"tier": "P1", "from": "To the Magnificent"}]},
        {"source": "tarasov.txt", "tier": "S1", "attribution": "Tarasov"},
    ])
    assert m["prince.txt"]["tier"] == "P1"
    assert m["prince.txt"]["attribution"] == "Machiavelli"
    assert m["prince.txt"]["regions"][0]["tier"] == "B"
    assert m["tarasov.txt"]["tier"] == "S1" and "regions" not in m["tarasov.txt"]


def _sources(tmp, files):
    sd = os.path.join(tmp, "sources")
    os.makedirs(sd, exist_ok=True)
    for name, text in files.items():
        open(os.path.join(sd, name), "w", encoding="utf-8").write(text)
    return sd


def test_validate_passes_when_markers_present():
    with tempfile.TemporaryDirectory() as t:
        sd = _sources(t, {"prince.txt": "INTRO bla\nTo the Magnificent Lorenzo\nbody text"})
        m = {"prince.txt": {"tier": "P1",
                            "regions": [{"tier": "B", "until": "To the Magnificent Lorenzo"},
                                        {"tier": "P1", "from": "To the Magnificent Lorenzo"}]}}
        res = validate_manifest(m, sd)
        assert res["ok"] is True and res["problems"] == []


def test_validate_catches_marker_not_in_source():
    # МОАТ-критично: маркер, которого нет в тексте дословно → тиры съедут молча
    with tempfile.TemporaryDirectory() as t:
        sd = _sources(t, {"prince.txt": "только тело без маркера"})
        m = {"prince.txt": {"tier": "P1", "regions": [{"tier": "P1", "from": "НЕТ ТАКОЙ СТРОКИ"}]}}
        res = validate_manifest(m, sd)
        assert res["ok"] is False
        assert any(p.get("marker") == "НЕТ ТАКОЙ СТРОКИ" for p in res["problems"])


def test_validate_catches_missing_file():
    with tempfile.TemporaryDirectory() as t:
        sd = _sources(t, {})
        res = validate_manifest({"ghost.txt": {"tier": "P1"}}, sd)
        assert res["ok"] is False
        assert any(p["issue"] == "file-missing" for p in res["problems"])


def test_validate_catches_invalid_tier():
    with tempfile.TemporaryDirectory() as t:
        sd = _sources(t, {"a.txt": "text"})
        res = validate_manifest({"a.txt": {"tier": "ZZZ"}}, sd)
        assert res["ok"] is False
        assert any("bad-tier" in p["issue"] for p in res["problems"])


def test_valid_tiers_constant():
    assert "P1" in VALID_TIERS and "S1" in VALID_TIERS and "A" in VALID_TIERS
