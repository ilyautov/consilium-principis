#!/usr/bin/env python3
"""Настройка FULL-тира (ollama + bge-m3) — чтобы юзер с чистой машины получил семантик-ретрив,
а не только лексический пол.

Ответственно: системный софт (ollama) молча НЕ ставим — даём точную OS-команду (это hard-to-reverse
outward-facing действие). Модель bge-m3 в УЖЕ стоящий ollama тянем авто (безопасно, идемпотентно).
  • probe()            — состояние: ollama запущен? bge-m3 скачан?
  • plan(state, plat)  — чистая логика → шаги {step, auto, cmd?, detail}
  • run_setup(consent) — выполнить авто-шаги (pull модели), для системных — напечатать инструкцию
"""
import sys
import json
import urllib.request
import subprocess

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"

INSTALL_HINTS = {
    "darwin": "поставь ollama: `brew install ollama` (или скачай https://ollama.com/download), затем `ollama serve`",
    "linux": "поставь ollama: `curl -fsSL https://ollama.com/install.sh | sh`, затем `ollama serve`",
    "windows": "скачай установщик ollama: https://ollama.com/download (download), запусти Ollama",
}


def _norm_platform(p):
    p = (p or "").lower()
    if "win" in p:
        return "windows"
    if "darwin" in p or "mac" in p:
        return "darwin"
    return "linux"


def probe():
    """{ollama_running, bge_m3_present} — без падений (нет сети → оба False)."""
    running, model = False, False
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as r:
            data = json.loads(r.read())
            running = True
            names = [m.get("name", "") for m in data.get("models", [])]
            model = any(EMBED_MODEL in n for n in names)
    except Exception:
        pass
    return {"ollama_running": running, "bge_m3_present": model}


def plan(state, platform):
    """Состояние + платформа → упорядоченные шаги. Системный софт — auto=False (инструкция)."""
    if not state["ollama_running"]:
        return [
            {"step": "ollama", "auto": False, "detail": INSTALL_HINTS.get(platform, INSTALL_HINTS["linux"])},
            {"step": "bge-m3", "auto": False, "detail": "после старта ollama: `ollama pull bge-m3`"},
        ]
    if not state["bge_m3_present"]:
        return [{"step": "bge-m3", "auto": True, "cmd": ["ollama", "pull", "bge-m3"],
                 "detail": "скачать модель эмбеддингов (~1.2GB) в установленный ollama"}]
    return [{"step": "ready", "auto": False, "detail": "ollama + bge-m3 на месте → FULL-тир доступен"}]


def run_setup(consent=True):
    """Выполнить план. Авто-шаги (pull модели) с consent; системные — печатаем инструкцию."""
    state = probe()
    steps = plan(state, _norm_platform(sys.platform))
    results = []
    for s in steps:
        if s.get("auto") and consent:
            try:
                subprocess.run(s["cmd"], check=True)
                results.append({**s, "ran": True})
            except Exception as e:
                results.append({**s, "ran": False, "error": str(e)})
        else:
            results.append({**s, "ran": False})
    return {"state": state, "results": results, "final": probe()}


if __name__ == "__main__":
    consent = "--no-pull" not in sys.argv
    out = run_setup(consent=consent)
    for r in out["results"]:
        tag = "✓ сделано" if r.get("ran") else ("→ " + r["detail"])
        print(f"  [{r['step']}] {tag}")
    f = out["final"]
    print(f"FULL-тир: {'✓ доступен' if (f['ollama_running'] and f['bge_m3_present']) else '✗ ещё нет (см. шаги выше)'}")
