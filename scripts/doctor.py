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
    return {"name": "skill-installed", "ok": bool(found), "advisory": True,
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


def check_judge():
    """§2.2 moat-v2: КТО судит релевантность цитат — честный лейбл уровня независимости
    (host = self-check заинтересованной стороны с решением в коде — легитимный пол, не
    болезнь → ok=True всегда; сам факт виден юзеру, как маркеры 🔵🟢🟡)."""
    try:
        import judge_backend
        i = judge_backend.info()
        return {"name": "judge", "ok": True, "detail": f"судья релевантности: {i['label']}"}
    except Exception as e:                             # диагностика не должна ронять doctor
        return {"name": "judge", "ok": True, "detail": f"судья релевантности: не определён ({e})"}


def check_calibration(root="."):
    """§3.2 moat-v2: per-advisor флаг автокалибровки порогов (build/calibration.json,
    пишет calibrate_advisor.py). «Не калиброван» — НЕ болезнь (глобальные дефолты
    действуют) → ok=True всегда; сам факт честно виден юзеру, как уровень судьи."""
    try:
        from corpusbuild.paths import corpus_path
        import engine
        import relevance_gate
        from engine.semantic import SemanticEngine
        adv_root = os.path.join(root, "advisors")
        parts = []
        if os.path.isdir(adv_root):
            for d in sorted(os.listdir(adv_root)):
                p = os.path.join(adv_root, d)
                if not (os.path.isdir(p) and os.path.isfile(corpus_path(p))):
                    continue
                raw = engine.load_calibration(p, validate_corpus=False)
                if not raw:
                    parts.append(f"{d}: не калиброван (глобальные дефолты)")
                    continue
                if engine.load_calibration(p) is None:  # staleness (review I-2)
                    parts.append(f"{d}: калиброван, но УСТАРЕЛ (корпус пересобран) — "
                                 "действуют глобальные дефолты; перезапусти calibrate_advisor")
                    continue
                t_raw = (raw.get("abstain_threshold") or {}).get("semantic")
                rg_raw = raw.get("relevance_gate") or {}
                s = (f"{d}: калиброван (t={t_raw}, полоса "
                     f"[{rg_raw.get('band_lo')}, {rg_raw.get('band_hi')}]")
                # РЕЗОЛВНУТЫЕ значения ≠ сырым → активен tighten-only floor (review I-1):
                # калибровка не может ослабить валидированные пороги — показываем оба.
                floors = []
                try:
                    t_res = engine.load_backend_threshold(
                        p, "semantic", SemanticEngine.DEFAULT_THRESHOLD)
                    if isinstance(t_raw, (int, float)) and abs(t_res - float(t_raw)) > 1e-9:
                        floors.append(f"t→{t_res} (floor)")
                except Exception:
                    pass
                try:
                    cfg = relevance_gate._gate_config(p)
                    hi_raw = rg_raw.get("band_hi")
                    if isinstance(hi_raw, (int, float)) and \
                            abs(cfg["band_hi"] - float(hi_raw)) > 1e-9:
                        floors.append(f"band_hi→{cfg['band_hi']} (floor)")
                except Exception:
                    pass
                if floors:
                    s += "; действует: " + ", ".join(floors)
                parts.append(s + ")")
        detail = "; ".join(parts) if parts else "нет собранных советников"
        return {"name": "calibration", "ok": True, "detail": detail}
    except Exception as e:                             # диагностика не роняет doctor
        return {"name": "calibration", "ok": True, "detail": f"не определено ({e})"}


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


def check_gov_anchors(root="."):
    """Якорь целостности (gov_heads.json в корне доски) против подмены советника ЦЕЛИКОМ.
    Три исхода на советника: якорь совпал (тихо ок) · якорь НЕ совпал (громкий провал:
    «цепь подменена целиком?») · якорь не зарегистрирован (предупреждение, НЕ провал —
    миграция: старые советники регистрируются одноразовым `governance.py freeze <dir>`)."""
    try:
        from corpusbuild.paths import corpus_path
        from governance import verify_advisor
        swapped, unregistered, verified = [], [], 0
        for sub in ("advisors", "lenses"):
            base = os.path.join(root, sub)
            if not os.path.isdir(base):
                continue
            for d in sorted(os.listdir(base)):
                p = os.path.join(base, d)
                if not (os.path.isdir(p) and os.path.isfile(corpus_path(p))):
                    continue
                res = verify_advisor(p, root=root)
                if res is None:
                    continue
                if res.get("swap_suspect") or res.get("anchor_match") is False:
                    swapped.append(f"{sub}/{d}")
                elif not res.get("anchor_registered"):
                    unregistered.append(f"{sub}/{d}")
                else:
                    verified += 1
        if swapped:
            return {"name": "gov-anchor", "ok": False,
                    "detail": ("✗ цепь подменена целиком? Советник самосогласован, но не совпадает "
                               f"с якорем доски: {', '.join(swapped)} — не доверяй цитатам, пересобери "
                               "из доверенных источников")}
        parts = [f"✓ якорь совпал: {verified}"] if verified else []
        if unregistered:
            parts.append("якорь не зарегистрирован (предупреждение): " + ", ".join(unregistered) +
                         " — закрепи: python scripts/governance.py freeze <dir>")
        return {"name": "gov-anchor", "ok": True,
                "detail": "; ".join(parts) if parts else "пропущен (нет собранных советников)"}
    except Exception as e:                             # диагностика не должна ронять doctor
        return {"name": "gov-anchor", "ok": True, "detail": f"не определено ({e})"}


def summarize(checks):
    # healthy = по СОДЕРЖАТЕЛЬНЫМ чекам; advisory (skill-installed) не роняет здоровье —
    # in-place из репо / MCP-режим работают без глобальной установки. Чек виден, но не блокирует.
    substantive = [c for c in checks if not c.get("advisory")]
    return {"healthy": all(c["ok"] for c in substantive), "checks": checks,
            "advisories": [c for c in checks if c.get("advisory") and not c["ok"]]}


def run_doctor(root="."):
    """Полный health-check. Контур тестируем на первом советнике с корпусом."""
    from corpusbuild.paths import corpus_path
    checks = [check_python(), check_skill_installed(), check_tier(), check_judge(),
              check_calibration(root), check_gov_anchors(root)]
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
    res = summarize(checks)
    # hint человеч. языком — хост показывает ЕГО, не сырые detail-строки (рв/fail-closed/tier/ollama)
    res["hint"] = ("Всё в порядке — можно звать совет." if res["healthy"]
                   else "Кое-что требует внимания, но базово совет работать может — скажи, помогу настроить.")
    return res


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
