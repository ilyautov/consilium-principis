"""§2.2 moat-v2: judge_backend — уровни независимости судьи релевантности + честный лейбл.

Массовый юзер (Claude-only, без ollama/API-ключа) сидит на lexical-тире, где серверного
судьи НЕТ. judge_backend резолвит, КТО судит релевантность:
  api    — независимый облачный (ключ в env; данные уходят провайдеру — честно в лейбле);
  ollama — независимый локальный;
  host   — self-check: судит сам хост (заинтересованная сторона), РЕШЕНИЕ остаётся в коде.
auto (дефолт): ollama жив → ollama; иначе host. НИКОГДА не облако молча (privacy 2026-07-18).
Облако (api) — только по ЯВНОМУ выбору: judge_backend="api" в конфиге или env-пин = согласие.
Явный выбор деградирует по цепочке api → ollama → host (host — пол: его fail-closed = 🟡).
Env-пин CONSILIUM_JUDGE_BACKEND — жёсткий (без пробинга): dev/тесты.

Все тесты оффлайн: llm_local.api_available / llm_local.available мокаются.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pytest
import judge_backend
import relevance_gate
import llm_local
from doctor import run_doctor


@pytest.fixture(autouse=True)
def _unpin(monkeypatch):
    """Снимаем сьютовый env-пин (conftest) — здесь тестируем саму резолюцию."""
    monkeypatch.delenv(judge_backend.ENV_PIN, raising=False)


def _avail(monkeypatch, api=False, ollama=False):
    monkeypatch.setattr(llm_local, "api_available", lambda: api)
    monkeypatch.setattr(llm_local, "available", lambda timeout=5: ollama)


def _cfg(monkeypatch, tmp_path, judge=None, extra=None):
    """Подменить board_config.json на tmp с relevance_gate.judge_backend=<judge>."""
    gate = dict(extra or {})
    if judge is not None:
        gate["judge_backend"] = judge
    p = tmp_path / "board_config.json"
    p.write_text(json.dumps({"relevance_gate": gate}), encoding="utf-8")
    monkeypatch.setattr(relevance_gate, "_config_path", lambda: str(p))


# ── матрица auto-резолюции: (api-ключ × ollama) ──
# ВАЖНО (privacy, 2026-07-18): auto НИКОГДА не уходит в облако молча, даже при наличии
# api-ключа. Облако = данные уходят провайдеру, а это ЯВНЫЙ выбор (config judge_backend=api
# / env-пин), не умолчание. До этой правки auto+ключ → api; реверс осознанный.

def test_auto_never_clouds_prefers_ollama_even_with_key(monkeypatch):
    _avail(monkeypatch, api=True, ollama=True)
    assert judge_backend.resolve() == "ollama"         # ключ есть, но auto не клауди → локальный ollama


def test_auto_key_but_ollama_down_resolves_host_not_cloud(monkeypatch):
    _avail(monkeypatch, api=True, ollama=False)
    assert judge_backend.resolve() == "host"           # ключ есть, ollama нет → host (пол), НЕ облако


def test_auto_no_key_ollama_up_resolves_ollama(monkeypatch):
    _avail(monkeypatch, api=False, ollama=True)
    assert judge_backend.resolve() == "ollama"


def test_auto_nothing_available_resolves_host(monkeypatch):
    _avail(monkeypatch, api=False, ollama=False)
    assert judge_backend.resolve() == "host"           # массовый Claude-only тир


# ── явный конфиг + деградация api → ollama → host ──

def test_explicit_api_with_key_resolves_api(monkeypatch, tmp_path):
    _avail(monkeypatch, api=True, ollama=True)
    _cfg(monkeypatch, tmp_path, judge="api")
    assert judge_backend.resolve() == "api"            # ЯВНЫЙ judge_backend=api = согласие на облако


def test_explicit_host_wins_even_with_judges_available(monkeypatch, tmp_path):
    _avail(monkeypatch, api=True, ollama=True)
    _cfg(monkeypatch, tmp_path, judge="host")
    assert judge_backend.resolve() == "host"


def test_explicit_api_without_key_degrades_to_ollama(monkeypatch, tmp_path):
    _avail(monkeypatch, api=False, ollama=True)
    _cfg(monkeypatch, tmp_path, judge="api")
    assert judge_backend.resolve() == "ollama"


def test_explicit_api_nothing_available_degrades_to_host(monkeypatch, tmp_path):
    _avail(monkeypatch, api=False, ollama=False)
    _cfg(monkeypatch, tmp_path, judge="api")
    assert judge_backend.resolve() == "host"


def test_explicit_ollama_down_degrades_to_host(monkeypatch, tmp_path):
    _avail(monkeypatch, api=True, ollama=False)        # ключ есть, но выбран ollama → api не берём
    _cfg(monkeypatch, tmp_path, judge="ollama")
    assert judge_backend.resolve() == "host"


def test_garbage_config_value_falls_back_to_auto(monkeypatch, tmp_path):
    _avail(monkeypatch, api=False, ollama=True)
    _cfg(monkeypatch, tmp_path, judge="gpt-5-please")
    assert judge_backend.resolve() == "ollama"         # мусор → auto-цепочка (fail-closed коэрс)


def test_gate_config_carries_judge_backend_default_auto(monkeypatch, tmp_path):
    _cfg(monkeypatch, tmp_path)                        # без ключа вовсе
    assert relevance_gate._gate_config()["judge_backend"] == "auto"


# ── env-пин: жёсткий, без пробинга (dev/тесты) ──

def test_env_pin_overrides_config_and_availability(monkeypatch, tmp_path):
    _avail(monkeypatch, api=True, ollama=False)
    _cfg(monkeypatch, tmp_path, judge="host")
    monkeypatch.setenv(judge_backend.ENV_PIN, "ollama")
    assert judge_backend.resolve() == "ollama"         # пин жёсткий: не пробим, не деградируем


def test_env_pin_garbage_ignored(monkeypatch):
    _avail(monkeypatch, api=False, ollama=False)
    monkeypatch.setenv(judge_backend.ENV_PIN, "чепуха")
    assert judge_backend.resolve() == "host"


# ── честные лейблы ──

def test_info_labels_are_honest(monkeypatch):
    _avail(monkeypatch, api=False, ollama=False)
    i = judge_backend.info()
    assert i["backend"] == "host" and i["independence"] == "self-check"
    assert "заинтересованная сторона" in i["label"] and "решение в коде" in i["label"]

    _avail(monkeypatch, api=False, ollama=True)
    i = judge_backend.info()
    assert i["backend"] == "ollama" and i["independence"] == "independent-local"
    assert "локальн" in i["label"]

    monkeypatch.setenv(judge_backend.ENV_PIN, "api")   # облако — только по явному согласию (пин)
    i = judge_backend.info()
    assert i["backend"] == "api" and i["independence"] == "independent-cloud"
    assert "облако" in i["label"] and "провайдеру" in i["label"]


# ── doctor показывает уровень судьи ──

def _judge_check(checks):
    return next(c for c in checks if c["name"] == "judge")


def test_doctor_shows_host_selfcheck_label(monkeypatch):
    monkeypatch.setenv(judge_backend.ENV_PIN, "host")
    r = run_doctor(ROOT)
    c = _judge_check(r["checks"])
    assert c["ok"] is True                             # host — легитимный пол, не болезнь
    assert "self-check" in c["detail"] and "заинтересованная" in c["detail"]


def test_doctor_shows_independent_labels(monkeypatch):
    monkeypatch.setenv(judge_backend.ENV_PIN, "ollama")
    assert "локальн" in _judge_check(run_doctor(ROOT)["checks"])["detail"]
    monkeypatch.setenv(judge_backend.ENV_PIN, "api")
    assert "облако" in _judge_check(run_doctor(ROOT)["checks"])["detail"]


# ── doctor: приватность ollama-эндпоинта (advisory, не болезнь) ──

def _ollama_check(checks):
    return next(c for c in checks if c["name"] == "ollama-endpoint")


def test_doctor_ollama_loopback_no_egress_warning(monkeypatch):
    monkeypatch.setattr(llm_local, "OLLAMA", "http://127.0.0.1:11434")
    c = _ollama_check(run_doctor(ROOT)["checks"])
    assert c["ok"] is True and c.get("advisory") is True
    assert "loopback" in c["detail"] and "не покидают" in c["detail"]


def test_doctor_ollama_remote_warns_data_leaves_machine(monkeypatch):
    monkeypatch.setattr(llm_local, "OLLAMA", "http://192.168.1.50:11434")
    c = _ollama_check(run_doctor(ROOT)["checks"])
    assert c["ok"] is True and c.get("advisory") is True   # легитимная возможность → не болезнь
    assert "НЕ loopback" in c["detail"] and "удалённ" in c["detail"]
