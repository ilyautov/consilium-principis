"""Приватность (§7) — Card живёт ТОЛЬКО в gitignore-зоне decisions/ под корнем доски.

Карта решения = полный вопрос + варианты + диапазоны + исходы = личные данные. Гард
фиксирует инвариант: Card-тул резолвит путь только под корнем (traversal-гард), отказывает
на пути вне корня, пишет исключительно в decisions/. Плюс: .gitignore реально прячет decisions/.
"""
import json
import os
import stat
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mcp_server import dispatch  # noqa: E402
import mcp_server  # noqa: E402


def _valid_map():
    return {
        "question": "Шипнуть или ждать?",
        "options": [
            {"id": "ship_public", "name": "Выпустить", "reversibility": "one-way"},
            {"id": "status_quo", "name": "Ничего", "reversibility": "two-way",
             "status_quo": True},
        ],
        "uncertainties": [
            {"id": "traction_prob", "kind": "event", "prob": 0.3, "confirmed_by_user": True},
            {"id": "upside_hours", "kind": "continuous", "min": 50, "mode": 150, "max": 400,
             "confirmed_by_user": True},
        ],
        "stakes": {"metric": "ценность в часах", "direction": "max"},
        "horizon": "3 месяца",
        "model": {
            "ship_public": {"expr": "traction_prob * upside_hours", "words": "трекшн × апсайд"},
            "status_quo": {"expr": "0", "words": "ноль"},
        },
    }


def test_card_written_under_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("save_decision_card", {"map": _valid_map(), "chosen_option": "ship_public",
                                        "review_horizon_days": 90, "slug": "ship-or-wait"})
    assert r.get("ok") is True, r
    assert r["path"].startswith("decisions/") and r["path"].endswith(".card.json")
    assert os.path.isfile(os.path.join(str(tmp_path), r["path"]))
    assert r["card_id"].startswith("dc_")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable on Windows")
def test_card_artifact_and_decisions_directory_are_private(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    saved = dispatch("save_decision_card", {"map": _valid_map(), "chosen_option": "ship_public",
                                             "review_horizon_days": 90, "slug": "private-card"})
    artifact = tmp_path / saved["path"]
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "decisions").stat().st_mode) == 0o700


def test_card_path_traversal_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    # злонамеренный slug с путём наружу — fail-closed отказ ДО записи (строгий слаг)
    r = dispatch("save_decision_card", {"map": _valid_map(), "chosen_option": "ship_public",
                                        "review_horizon_days": 90, "slug": "../../etc/evil"})
    assert "error" in r
    # ничего не записано вне корня
    assert not os.path.exists(os.path.join(str(tmp_path), "..", "..", "etc", "evil.card.json"))


def test_card_collision_gets_suffix_not_overwrite(tmp_path, monkeypatch):
    """Коллизия имени Card → суффикс -2, а не перезапись (тот же контракт, что у карты)."""
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    a = dispatch("save_decision_card", {"map": _valid_map(), "chosen_option": "ship_public",
                                        "review_horizon_days": 90, "slug": "same"})
    b = dispatch("save_decision_card", {"map": _valid_map(), "chosen_option": "ship_public",
                                        "review_horizon_days": 90, "slug": "same"})
    assert a.get("ok") and b.get("ok")
    assert a["path"] != b["path"]
    assert os.path.isfile(os.path.join(str(tmp_path), a["path"]))
    assert os.path.isfile(os.path.join(str(tmp_path), b["path"]))


def test_close_card_path_traversal_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    r = dispatch("close_decision_card", {"path": "../../etc/passwd",
                                         "outcome": {"resolved_on": "2026-10-01",
                                                     "occurred": True}})
    assert "error" in r


def test_gitignore_hides_decisions():
    gi = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "decisions/" in gi, "decisions/ обязан быть в .gitignore (личные данные решений)"


def test_close_and_calibration_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    save = dispatch("save_decision_card", {"map": _valid_map(), "chosen_option": "ship_public",
                                           "review_horizon_days": 90, "form": "event"})
    cid = save["card_id"]
    close = dispatch("close_decision_card", {"card_id": cid,
                                             "outcome": {"resolved_on": "2026-10-20",
                                                         "occurred": True, "endorsed": True}})
    assert close.get("ok") is True, close
    # закрытая карта попадает в числовую калибровку
    cal = dispatch("prediction_calibration", {})
    assert cal["closed"] == 1
    saved = json.load(open(os.path.join(str(tmp_path), save["path"]), encoding="utf-8"))
    assert saved["outcome"]["occurred"] is True
