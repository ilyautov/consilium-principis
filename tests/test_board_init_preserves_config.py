"""board_init НЕ затирает пользовательские настройки board_config.json (security-ревью M2).

install.py обещает: «board_config.json — user-data, никогда не затирается переустановкой»,
а board_init писал файл с нуля → каждое обновление скилла молча сбрасывало abstain_threshold,
hybrid_alpha, language и т.п., выставленные через config_set. Теперь: машинные ключи
(semantic_available, token_threshold, advisors) пересчитываются, остальное сохраняется;
--reset и явный --abstain-threshold перекрывают осознанно.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "board_init.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import board_init  # noqa: E402


def _run(tmp_path, *extra):
    (tmp_path / "advisors" / "sage").mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, SCRIPT, str(tmp_path / "advisors"),
                        "--semantic-available", "false", *extra],
                       capture_output=True, text=True, cwd=str(tmp_path),
                       env={**os.environ, "OLLAMA_HOST": "http://127.0.0.1:59999"})
    assert r.returncode == 0, r.stdout + r.stderr
    return json.load(open(tmp_path / "board_config.json", encoding="utf-8")), r.stdout


def test_rerun_keeps_user_keys_and_recomputes_machine_keys(tmp_path):
    cfg, _ = _run(tmp_path)
    assert cfg["advisors"] == {"sage": cfg["advisors"]["sage"]} and cfg["semantic_available"] is False
    # пользователь подкрутил через config_set (скалярный порог, как пишет тул) + чужие ключи
    cfg.update({"abstain_threshold": 0.33, "hybrid_alpha": 0.7, "language": "en",
                "interface_mode": "widget", "chunk_chars": 777, "advisors": {"stale": {}}})
    (tmp_path / "board_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp_path / "advisors" / "second").mkdir()
    cfg2, out = _run(tmp_path, "--semantic-available", "true")
    assert cfg2["abstain_threshold"] == 0.33 and cfg2["hybrid_alpha"] == 0.7
    assert cfg2["language"] == "en" and cfg2["interface_mode"] == "widget"
    assert cfg2["chunk_chars"] == 777                       # корпус нарезан под него — не трогаем
    assert set(cfg2["advisors"]) == {"sage", "second"}      # машинные ключи пересчитаны
    assert cfg2["semantic_available"] is True
    assert "сохранены настройки" in out and "hybrid_alpha" in out


def test_reset_flag_rebuilds_from_scratch(tmp_path):
    _run(tmp_path)
    p = tmp_path / "board_config.json"
    p.write_text(json.dumps({"hybrid_alpha": 0.9, "abstain_threshold": 0.1}), encoding="utf-8")
    cfg, _ = _run(tmp_path, "--reset")
    assert "hybrid_alpha" not in cfg and isinstance(cfg["abstain_threshold"], dict)


def test_explicit_abstain_threshold_overrides_saved_dict(tmp_path):
    _run(tmp_path)
    p = tmp_path / "board_config.json"
    p.write_text(json.dumps({"abstain_threshold": {"semantic": 0.2, "lexical": 0.1}}), encoding="utf-8")
    cfg, _ = _run(tmp_path, "--abstain-threshold", "0.6")
    assert cfg["abstain_threshold"]["semantic"] == 0.6      # явный флаг = осознанное решение


def test_merge_fills_missing_tiers_without_touching_user_tiers():
    existing = {"abstain_threshold": {"semantic": 0.2}}
    computed = {"abstain_threshold": {"semantic": 0.5, "lexical": 0.3},
                "semantic_available": True, "token_threshold": 1, "advisors": {}}
    merged = board_init.merge_config(existing, computed)
    assert merged["abstain_threshold"] == {"semantic": 0.2, "lexical": 0.3}


def test_corrupt_or_missing_config_is_not_fatal(tmp_path):
    p = tmp_path / "board_config.json"
    p.write_text("{not json", encoding="utf-8")
    cfg, _ = _run(tmp_path)
    assert isinstance(cfg["advisors"], dict)
    assert board_init.load_existing_config(str(tmp_path / "nope.json")) == {}
