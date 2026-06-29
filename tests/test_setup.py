"""Настройка FULL-тира (ollama + bge-m3) при установке — чтобы юзер с чистой машины получил
семантик-ретрив, а не только пол.

Ответственно: системный софт (ollama) молча НЕ ставим — даём точную OS-команду. Модель bge-m3
в уже стоящий ollama тянем авто (безопасно, идемпотентно). plan() — чистая логика: по состоянию
(ollama запущен? модель есть?) и платформе выдаёт шаги {step, auto, cmd?, detail}.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from setup_full import plan, probe


def test_plan_ready_when_all_present():
    steps = plan({"ollama_running": True, "bge_m3_present": True}, "darwin")
    assert len(steps) == 1 and steps[0]["step"] == "ready"


def test_plan_auto_pull_when_ollama_up_no_model():
    steps = plan({"ollama_running": True, "bge_m3_present": False}, "linux")
    pull = [s for s in steps if s["step"] == "bge-m3"][0]
    assert pull["auto"] is True and pull["cmd"] == ["ollama", "pull", "bge-m3"]


def test_plan_manual_install_when_ollama_absent():
    steps = plan({"ollama_running": False, "bge_m3_present": False}, "darwin")
    ol = [s for s in steps if s["step"] == "ollama"][0]
    assert ol["auto"] is False                       # системный софт не ставим молча
    assert "ollama.com" in ol["detail"] or "brew" in ol["detail"]


def test_plan_platform_specific_hint():
    assert "install.sh" in plan({"ollama_running": False, "bge_m3_present": False}, "linux")[0]["detail"]
    assert "download" in plan({"ollama_running": False, "bge_m3_present": False}, "windows")[0]["detail"].lower()


def test_probe_returns_shape():
    p = probe()
    assert set(p) == {"ollama_running", "bge_m3_present"}
    assert isinstance(p["ollama_running"], bool) and isinstance(p["bge_m3_present"], bool)
