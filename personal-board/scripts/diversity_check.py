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

def main():
    paths = sys.argv[1:]
    if len(paths) < 2:
        print("Дай минимум 2 советников: python diversity_check.py advisors/x advisors/y ...", file=sys.stderr)
        sys.exit(1)
    advisors = [a for a in (load_advisor(p) for p in paths) if a]
    if len(advisors) < 2:
        print("Не нашёл persona.md минимум у двоих.", file=sys.stderr)
        sys.exit(1)

    print(f"Состав совета ({len(advisors)}):")
    for a in advisors:
        print(f"  · {a['name']}: линзы {sorted(a['lenses'])}")

    sims = []
    print("\nПопарное перекрытие (линзы взвешены ×2, домены ×1):")
    for x, y in itertools.combinations(advisors, 2):
        lj = jaccard(x["lenses"], y["lenses"])
        dj = jaccard(x["domains"], y["domains"])
        sim = (2 * lj + dj) / 3
        sims.append((sim, x, y, lj, dj))
        flag = "  🚩 дубль голоса" if sim >= 0.5 else ("  ⚠️ близки" if sim >= 0.34 else "")
        print(f"  {x['name']} ↔ {y['name']}: similarity {sim:.2f} (линзы {lj:.2f}, домены {dj:.2f}){flag}")

    mean_sim = sum(s[0] for s in sims) / len(sims)
    diversity = 1 - mean_sim
    print(f"\nDiversity score: {diversity:.2f}  (1.0 = полностью ортогональны, 0 = клоны)")

    if diversity >= 0.7:
        verdict = "✅ здоровое разнообразие — углы реально разные"
    elif diversity >= 0.5:
        verdict = "⚠️ приемлемо, но есть перекрытия — проверь флаги ниже"
    else:
        verdict = "🚩 ЭХО-КАМЕРА: состав думает слишком похоже, совет даст ложный консенсус"
    print(verdict)

    # рекомендации по оси
    redundant = [s for s in sims if s[0] >= 0.5]
    if redundant:
        print("\nИзбыточные пары (один можно заменить на контр-голос):")
        for sim, x, y, lj, dj in redundant:
            print(f"  · {x['name']} и {y['name']} (sim {sim:.2f}) — оставь одного, добавь кого-то с другой осью")
    # какие оси НЕ покрыты (грубая эвристика — частые ортогональные оси)
    covered = set().union(*[a["lenses"] for a in advisors])
    axes_hint = {
        "скепсис/risk": {"инверсия", "memento-mori", "pre-mortem", "via-negativa"},
        "оптимизм/рост": {"compounding", "четыре-леверижа", "judgment-over-effort"},
        "антихрупкость/хаос": {"barbell", "optionality", "black-swan"},
        "этика/смысл": {"дихотомия-контроля", "externals-as-indifferent", "is-this-necessary"},
        "системы/2-й порядок": {"second-order", "mental-models", "incentives"},
    }
    missing = [ax for ax, kws in axes_hint.items() if not (covered & kws)]
    if missing:
        print(f"\nНе покрытые оси мышления (кандидаты добавить для разнообразия): {', '.join(missing)}")

if __name__ == "__main__":
    main()
