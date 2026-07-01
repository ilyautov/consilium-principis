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
