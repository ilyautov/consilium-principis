"""llm_local — общий фасад LLM: generate идёт через мокаемый _raw_generate (тесты без сети);
available() не падает при мёртвом ollama."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import llm_local


def test_generate_routes_through_mockable_seam(monkeypatch):
    seen = {}

    def fake(prompt, model, temperature, timeout):
        seen.update(prompt=prompt, model=model, temperature=temperature)
        return "MOCKED"

    monkeypatch.setattr(llm_local, "_raw_generate", fake)
    out = llm_local.generate("hi", model="m", temperature=0.7)
    assert out == "MOCKED"
    assert seen["prompt"] == "hi" and seen["model"] == "m" and seen["temperature"] == 0.7


def test_generate_defaults_model(monkeypatch):
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: m)
    assert llm_local.generate("x") == llm_local.GEN_MODEL   # дефолт-модель подставлена


def test_available_no_crash_when_ollama_down(monkeypatch):
    monkeypatch.setattr(llm_local, "OLLAMA", "http://127.0.0.1:59999")
    assert llm_local.available(timeout=1) is False          # мёртвый порт → False, без исключения


# --- OpenRouter-бэкенд (LLM_BACKEND=openrouter): роутинг + fail-closed фоллбэк ---

def test_backend_default_is_ollama_untouched(monkeypatch):
    """Без LLM_BACKEND generate идёт через ollama-seam и НЕ трогает openrouter."""
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: "OLLAMA")
    monkeypatch.setattr(llm_local, "_raw_generate_openrouter",
                        lambda p, m, t, to: (_ for _ in ()).throw(AssertionError("не должен вызываться")))
    assert llm_local.generate("x") == "OLLAMA"


def test_backend_openrouter_routes_and_defaults_model_from_env(monkeypatch):
    """LLM_BACKEND=openrouter → _raw_generate_openrouter; дефолт-модель из LLM_API_MODEL."""
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_MODEL", "vendor/some-model")
    seen = {}

    def fake_or(prompt, model, temperature, timeout):
        seen.update(prompt=prompt, model=model, temperature=temperature)
        return "API"

    monkeypatch.setattr(llm_local, "_raw_generate_openrouter", fake_or)
    monkeypatch.setattr(llm_local, "_raw_generate",
                        lambda p, m, t, to: (_ for _ in ()).throw(AssertionError("ollama не должен вызываться")))
    assert llm_local.generate("hi", temperature=0.1) == "API"
    assert seen["model"] == "vendor/some-model" and seen["prompt"] == "hi" and seen["temperature"] == 0.1


def test_backend_openrouter_explicit_model_wins(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_MODEL", "vendor/env-model")
    monkeypatch.setattr(llm_local, "_raw_generate_openrouter", lambda p, m, t, to: m)
    assert llm_local.generate("x", model="vendor/explicit") == "vendor/explicit"


def test_backend_openrouter_falls_back_to_ollama_on_exception(monkeypatch):
    """API упал → fail-closed фоллбэк на локальный ollama-seam."""
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_MODEL", "vendor/some-model")
    monkeypatch.setattr(llm_local, "_raw_generate_openrouter",
                        lambda p, m, t, to: (_ for _ in ()).throw(RuntimeError("api down")))
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: "FALLBACK")
    assert llm_local.generate("x") == "FALLBACK"


def test_backend_openrouter_missing_key_goes_straight_to_ollama(monkeypatch):
    """Нет OPENROUTER_API_KEY → openrouter даже не пробуем, сразу ollama."""
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_MODEL", "vendor/some-model")
    monkeypatch.setattr(llm_local, "_raw_generate_openrouter",
                        lambda p, m, t, to: (_ for _ in ()).throw(AssertionError("без ключа не должен вызываться")))
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: "OLLAMA")
    assert llm_local.generate("x") == "OLLAMA"


def test_backend_openrouter_both_fail_raises(monkeypatch):
    """API упал И ollama упал → исключение наружу (вызыватели трактуют как gated/withheld)."""
    import pytest
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_MODEL", "vendor/some-model")
    monkeypatch.setattr(llm_local, "_raw_generate_openrouter",
                        lambda p, m, t, to: (_ for _ in ()).throw(RuntimeError("api down")))
    monkeypatch.setattr(llm_local, "_raw_generate",
                        lambda p, m, t, to: (_ for _ in ()).throw(RuntimeError("ollama down")))
    with pytest.raises(Exception):
        llm_local.generate("x")


def test_api_available_iff_key_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert llm_local.api_available() is True
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert llm_local.api_available() is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert llm_local.api_available() is False               # пустой ключ = нет ключа
