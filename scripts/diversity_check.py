#!/usr/bin/env python3
"""
diversity_check.py — проверка ортогональности состава совета.

Заблуждение, которое чинит (см. ARCHITECTURE раздел 15, #6):
пять техно-оптимистов = уверенная эхо-камера под видом совета. Разнообразие
важнее количества (ресёрч, ось 3). Скрипт читает lenses/domains из persona.md
каждого выбранного советника, считает попарное пересечение (Jaccard) и:
  - выдаёт diversity score (0..1, выше = разнообразнее);
  - флагует пары с высоким перекрытием (кандидаты на «один и тот же голос»);
  - предупреждает, если состав = эхо-камера, и советует, кого добавить по оси.

Использование:
  python diversity_check.py advisors/munger advisors/naval advisors/marcus-aurelius
"""
import sys, os, re, itertools

def parse_frontmatter_list(text, key):
    # ищем строку 'key: [a, b, c]' внутри первого --- ... --- блока
    m = re.search(r"^---\s*(.*?)\s*^---", text, re.S | re.M)
    block = m.group(1) if m else text
    km = re.search(rf"^{key}:\s*\[(.*?)\]", block, re.M)
    if not km:
        return []
    items = [x.strip().strip("'\"") for x in km.group(1).split(",")]
    return [x for x in items if x]

def load_advisor(path):
    pm = os.path.join(path, "persona.md")
    if not os.path.isfile(pm):
        return None
    with open(pm, encoding="utf-8") as f:
        t = f.read()
    name = re.search(r"^name:\s*(.+)$", t, re.M)
    return {
        "name": name.group(1).strip() if name else os.path.basename(path),
        "lenses": set(parse_frontmatter_list(t, "lenses")),
        "domains": set(parse_frontmatter_list(t, "domains")),
    }

def jaccard(a, b):
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b) if (a | b) else 0.0

# грубая эвристика — частые ортогональные оси мышления (для missing_axes)
_AXES_HINT = {
    "скепсис/risk": {"инверсия", "memento-mori", "pre-mortem", "via-negativa"},
    "оптимизм/рост": {"compounding", "четыре-леверижа", "judgment-over-effort"},
    "антихрупкость/хаос": {"barbell", "optionality", "black-swan"},
    "этика/смысл": {"дихотомия-контроля", "externals-as-indifferent", "is-this-necessary"},
    "системы/2-й порядок": {"second-order", "mental-models", "incentives"},
}

def check(paths):
    """Ортогональность состава совета → dict (без печати). paths — abs пути advisor'ов.
    <2 валидных persona.md → {"error": ...}. Если у ≥2 советников пусты И lenses,
    И domains — метаданных нет, судить нельзя: verdict="insufficient_data",
    diversity=None (fail-closed: без фронтматера similarity-математика выдавала бы
    ложное 1.0/«ok» — финальное ревью 2026-07-20, Minor-2)."""
    advisors = [a for a in (load_advisor(p) for p in paths) if a]
    if len(advisors) < 2:
        return {"error": "Не нашёл persona.md минимум у двоих."}
    bare = [a["name"] for a in advisors if not a["lenses"] and not a["domains"]]
    if len(bare) >= 2:
        return {"advisors": [a["name"] for a in advisors], "pairs": [],
                "diversity": None, "verdict": "insufficient_data", "missing_axes": [],
                "hint": ("Недостаточно данных: у %d советников (%s) нет ни lenses, ни domains "
                         "во фронтматере persona.md — разнообразие судить нельзя. "
                         "Заполни метаданные (lenses/domains) и перезапусти."
                         % (len(bare), ", ".join(bare)))}
    pairs = []
    for x, y in itertools.combinations(advisors, 2):
        lj, dj = jaccard(x["lenses"], y["lenses"]), jaccard(x["domains"], y["domains"])
        sim = (2 * lj + dj) / 3
        flag = "dup" if sim >= 0.5 else ("close" if sim >= 0.34 else "")
        pairs.append({"a": x["name"], "b": y["name"], "similarity": round(sim, 3),
                      "lenses_j": round(lj, 3), "domains_j": round(dj, 3), "flag": flag})
    mean_sim = sum(p["similarity"] for p in pairs) / len(pairs)
    diversity = round(1 - mean_sim, 3)
    verdict = ("ok" if diversity >= 0.7 else
               "overlap" if diversity >= 0.5 else "echo_chamber")
    covered = set().union(*[a["lenses"] for a in advisors])
    missing = [ax for ax, kws in _AXES_HINT.items() if not (covered & kws)]
    return {"advisors": [a["name"] for a in advisors], "pairs": pairs,
            "diversity": diversity, "verdict": verdict, "missing_axes": missing}

_VERDICT_LINE = {
    "ok": "✅ здоровое разнообразие — углы реально разные",
    "overlap": "⚠️ приемлемо, но есть перекрытия — проверь флаги ниже",
    "echo_chamber": "🚩 ЭХО-КАМЕРА: состав думает слишком похоже, совет даст ложный консенсус",
}

def main():
    paths = sys.argv[1:]
    if len(paths) < 2:
        print("Дай минимум 2 советников: python diversity_check.py advisors/x advisors/y ...", file=sys.stderr)
        sys.exit(1)
    out = check(paths)
    if "error" in out:
        print(out["error"], file=sys.stderr)
        sys.exit(1)

    advisors = [a for a in (load_advisor(p) for p in paths) if a]  # для показа линз
    print(f"Состав совета ({len(advisors)}):")
    for a in advisors:
        print(f"  · {a['name']}: линзы {sorted(a['lenses'])}")

    if out["verdict"] == "insufficient_data":
        # метаданных нет — судить нельзя: честный hint вместо ложного score 1.0
        print(f"\n⚠️ {out['hint']}")
        return

    print("\nПопарное перекрытие (линзы взвешены ×2, домены ×1):")
    for p in out["pairs"]:
        flag = ("  🚩 дубль голоса" if p["flag"] == "dup"
                else ("  ⚠️ близки" if p["flag"] == "close" else ""))
        print(f"  {p['a']} ↔ {p['b']}: similarity {p['similarity']:.2f} "
              f"(линзы {p['lenses_j']:.2f}, домены {p['domains_j']:.2f}){flag}")

    print(f"\nDiversity score: {out['diversity']:.2f}  (1.0 = полностью ортогональны, 0 = клоны)")
    print(_VERDICT_LINE[out["verdict"]])

    # рекомендации по оси
    redundant = [p for p in out["pairs"] if p["flag"] == "dup"]
    if redundant:
        print("\nИзбыточные пары (один можно заменить на контр-голос):")
        for p in redundant:
            print(f"  · {p['a']} и {p['b']} (sim {p['similarity']:.2f}) — оставь одного, добавь кого-то с другой осью")
    if out["missing_axes"]:
        print(f"\nНе покрытые оси мышления (кандидаты добавить для разнообразия): {', '.join(out['missing_axes'])}")

if __name__ == "__main__":
    main()
