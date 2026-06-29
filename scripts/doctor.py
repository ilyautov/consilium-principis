"""Health-check «работает ли у меня вообще?» для юзера с нуля + отчёт о тире ретрива.

install.py копирует файлы, но юзер не знает, здоров ли результат. Проверки:
  • check_python      — Python ≥3.10 (критично)
  • check_skill_installed — скилл виден в ~/.claude/skills (иначе /board не появится)
  • check_tier        — FULL (semantic/ollama) или SIMPLE (лексика; контур цел и без ollama → ok)
  • check_contour     — САМОТЕСТ РВА: дословный P1-фрагмент matchнулся, фейк → None (критично, если есть корпус)
report() (отчёт о тире) сохранён для обратной совместимости.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/ — engine это пакет


def check_python():
    ok = sys.version_info >= (3, 10)
    return {"name": "python", "ok": ok,
            "detail": f"{sys.version_info.major}.{sys.version_info.minor} (нужно ≥3.10)"}


_SKILL_KEYS = ("consilium", "principis", "personal-board")


def check_skill_installed(skills_home=None):
    """Ищет ИМЕННО Consilium в ~/.claude/skills (а не любой скилл)."""
    home = skills_home or os.path.join(os.path.expanduser("~"), ".claude", "skills")
    found = []
    if os.path.isdir(home):
        for d in sorted(os.listdir(home)):
            if os.path.isfile(os.path.join(home, d, "SKILL.md")) and \
               any(k in d.lower() for k in _SKILL_KEYS):
                found.append(d)
    return {"name": "skill-installed", "ok": bool(found),
            "detail": ", ".join(found) if found
                      else f"Consilium не найден в {home} (запусти install.py, либо работаешь in-place из репо)"}


def check_tier():
    try:
        from engine.semantic import SemanticEngine
        sem = SemanticEngine.available()
    except Exception:
        sem = False
    return {"name": "tier", "ok": True,  # SIMPLE — норма, контур цел
            "detail": "FULL (semantic, bge-m3)" if sem else "SIMPLE (лексика; контур цел без ollama)"}


def check_contour(advisor_dir):
    """Самотест рва на конкретном советнике. ok=True если фрагмент P1 matchнулся и фейк→None,
    либо пропущен (нет корпуса с P1 — нечего тестировать)."""
    from corpusbuild.paths import corpus_path
    from engine.fidelity import best_match
    import json
    cp = corpus_path(advisor_dir)
    if not os.path.isfile(cp):
        return {"name": "contour", "ok": True, "detail": "пропущен (нет корпуса)"}
    p1_text = None
    with open(cp, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("tier") == "P1" and len(r.get("text", "")) > 40:
                p1_text = r["text"]
                break
    if not p1_text:
        return {"name": "contour", "ok": True, "detail": "пропущен (нет P1-чанка)"}
    frag = p1_text[10:50].strip()
    real = best_match(frag, advisor_dir)
    fake = best_match("выдуманная цитата которой нет в этом корпусе про блокчейн", advisor_dir)
    ok = (real is not None and real[0] in ("P1", "P2")) and fake is None
    return {"name": "contour", "ok": ok,
            "detail": "✓ дословный→🔵, фейк→fail-closed" if ok else "✗ рв не держит — проверь корпус/тиры"}


def summarize(checks):
    return {"healthy": all(c["ok"] for c in checks), "checks": checks}


def run_doctor(root="."):
    """Полный health-check. Контур тестируем на первом советнике с корпусом."""
    from corpusbuild.paths import corpus_path
    checks = [check_python(), check_skill_installed(), check_tier()]
    adv_root = os.path.join(root, "advisors")
    tested = False
    if os.path.isdir(adv_root):
        for d in sorted(os.listdir(adv_root)):
            p = os.path.join(adv_root, d)
            if os.path.isdir(p) and os.path.isfile(corpus_path(p)):
                checks.append(check_contour(p))
                tested = True
                break
    if not tested:
        checks.append({"name": "contour", "ok": True, "detail": "пропущен (нет собранных советников)"})
    return summarize(checks)


def report():
    """Отчёт о тире (обратная совместимость)."""
    from engine.semantic import SemanticEngine
    from engine import load_config_value
    sem = SemanticEngine.available()
    mode = load_config_value("retrieval_mode", "auto")
    if sem:
        tier = "FULL — hybrid (semantic ∪ lexical, RRF)" if mode == "hybrid" else "FULL (semantic, bge-m3)"
    else:
        tier = "SIMPLE (lexical floor)"
    print("Consilium-Principis — диагностика движка")
    print(f"  ollama/bge-m3 (semantic): {'✓ доступен' if sem else '✗ нет'}")
    print(f"  → активный tier: {tier}")
    if not sem:
        print("  fidelity-контур: ✓ работает и на полу (verbatim-чек не требует ollama)")
        print("  поднять до FULL: запустить ollama + `ollama pull bge-m3`, затем build_index")


if __name__ == "__main__":
    report()
