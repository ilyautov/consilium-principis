#!/usr/bin/env python3
"""A/B-калибровка подачи под человека (N=1), с guardrail не-захвата.

Слой Принцепс хранит interface_mode (rigor/support) — КАК совет говорит с юзером. Калибровка
идёт дальше: эмпирически выбирает фрейминг подачи по ИСХОДАМ решений этого юзера.

Два фрейминга одного и того же контента совета:
  • светлый (light) — под когницию: опции, трение, сократично. Юзер думает сам (не-захват).
  • тёмный (dark)  — под комплаенс: директивно, один путь, минимум трения. Граница манипуляции.

Метрика — НЕ «послушался ли» (это и есть ловушка захвата), а ОДОБРИЛ ли юзер исход задним
числом. Guardrail: если тёмный гонит действие (success по факту), но проигрывает по одобрению
— это захват; рекомендуем светлый, не оптимизируем под краткосрочный комплаенс.
Источник данных — журнал решений (principis.md / relationship.md), записи `### …` с полями
Подача / ИСХОД / Одобрено. Ядро чистое (на вход — распарсенные записи) → детерминированно.
"""
import re

LIGHT_MARKERS = ("светл", "light", "когниц")
DARK_MARKERS = ("тёмн", "темн", "dark", "комплаенс")
DEFAULT_FRAMING = "light"          # дефолт безопасен: не-захват


def classify_framing(s):
    """Строка → 'light' | 'dark' | None."""
    low = s.lower()
    if any(m in low for m in DARK_MARKERS):
        return "dark"
    if any(m in low for m in LIGHT_MARKERS):
        return "light"
    return None


def _outcome_of(block):
    """Статус ИСХОДА в блоке записи: 'good' (✅) | 'bad' (❌) | 'pending' (⏳/pending) | None."""
    m = re.search(r"(?im)^\s*[-*]?\s*\**\s*ИСХОД.*$", block)
    if not m:
        return None
    line = m.group(0)
    if re.search(r"⏳|pending", line, re.I):
        return "pending"
    if "✅" in line:
        return "good"
    if "❌" in line:
        return "bad"
    return "pending"               # ИСХОД есть, но без явного знака → ещё не закрыт


def _endorsed_of(block):
    """Одобрил ли юзер исход задним числом: True | False | None (не указано)."""
    m = re.search(r"(?im)^.*Одобрено.*$", block)
    if not m:
        return None
    return not re.search(r"\bнет\b|\bno\b", m.group(0), re.I)


def parse_decision_log(text):
    """Журнал → записи [{title, framing, outcome, endorsed}]. Запись = блок после '### '."""
    entries = []
    blocks = re.split(r"(?m)^###\s+", text)[1:]
    for blk in blocks:
        title = blk.splitlines()[0].strip() if blk.strip() else ""
        fr = None
        m = re.search(r"(?im)^.*Подача.*$|^.*framing.*$", blk)
        if m:
            fr = classify_framing(m.group(0))
        entries.append({
            "title": title, "framing": fr,
            "outcome": _outcome_of(blk), "endorsed": _endorsed_of(blk),
        })
    return entries


def _blank_stats():
    return {"n": 0, "resolved": 0, "good": 0, "endorsed": 0,
            "success_rate": 0.0, "endorse_rate": 0.0}


def calibrate(entries):
    """Per-framing статистика + рекомендация + capture_flag.

    success_rate = good / resolved (исход хороший по факту).
    endorse_rate = endorsed / resolved (юзер одобрил задним числом) — ГЛАВНАЯ метрика.
    recommend = фрейминг с макс endorse_rate; тай/нет данных → light (безопасный дефолт).
    capture_flag = dark обгоняет по success, но отстаёт по endorse (гонит действие, юзер жалеет)
                   → рекомендуем light несмотря на «успех».
    """
    by = {"light": _blank_stats(), "dark": _blank_stats()}
    for e in entries:
        fr = e["framing"]
        if fr not in by:
            continue
        s = by[fr]
        s["n"] += 1
        if e["outcome"] in ("good", "bad"):
            s["resolved"] += 1
            if e["outcome"] == "good":
                s["good"] += 1
            if e["endorsed"]:
                s["endorsed"] += 1
    for s in by.values():
        if s["resolved"]:
            s["success_rate"] = s["good"] / s["resolved"]
            s["endorse_rate"] = s["endorsed"] / s["resolved"]

    L, D = by["light"], by["dark"]
    # захват: у тёмного ДЕЙСТВИЕ обгоняет ОДОБРЕНИЕ (regret-разрыв) и светлый лучше по одобрению.
    capture_flag = (D["resolved"] > 0 and D["success_rate"] > D["endorse_rate"]
                    and D["endorse_rate"] < L["endorse_rate"])
    if capture_flag:
        recommend, reason = "light", ("тёмный гонит действие, но юзер не одобряет исход "
                                      "задним числом → захват; держим светлый")
    elif D["endorse_rate"] > L["endorse_rate"] and D["resolved"] > 0:
        recommend, reason = "dark", "тёмный честно ведёт к ОДОБРЕННЫМ исходам у этого юзера"
    elif L["endorse_rate"] > D["endorse_rate"] and L["resolved"] > 0:
        recommend, reason = "light", "светлый ведёт к одобренным исходам у этого юзера"
    else:
        recommend, reason = DEFAULT_FRAMING, "данных мало → безопасный дефолт (не-захват)"

    return {"by_framing": by, "recommend": recommend,
            "capture_flag": capture_flag, "reason": reason}


if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 2:
        print("Использование: python calibration.py <principis.md | relationship.md>")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"[calibration] нет файла: {path}")
        sys.exit(1)
    cal = calibrate(parse_decision_log(open(path, encoding="utf-8").read()))
    for fr in ("light", "dark"):
        s = cal["by_framing"][fr]
        label = "светлый" if fr == "light" else "тёмный"
        print(f"  {label}: записей {s['n']} · resolved {s['resolved']} · "
              f"success {s['success_rate']*100:.0f}% · одобрено {s['endorse_rate']*100:.0f}%")
    if cal["capture_flag"]:
        print("  ⚠ ЗАХВАТ: тёмный гонит действие, юзер жалеет задним числом.")
    print(f"  → рекомендация подачи: {cal['recommend'].upper()} — {cal['reason']}")
