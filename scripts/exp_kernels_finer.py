#!/usr/bin/env python3
"""B: добить асимметрию Макиавелли (64% vs 91% Аврелия) — гетерогенному корпусу нужны тоньше кернелы?

Гипотеза: плоские 6 кернелов недо-фитят Prince+Discourses (трактат+нарратива). Тест с контролем
confound'а «больше кернелов ≠ структура»:
  • flat-6      — базлайн (как в exp_kernels);
  • flat-12     — больше кернелов, БЕЗ структуры (контроль на счёт);
  • per-source  — 6 на Prince + 6 на Discourses (структура по под-корпусам).
Если per-source > flat-12 — помогает именно СТРУКТУРА, не число. Валидация: held-out own-win
против ФИКСИРОВАННЫХ кернелов Аврелия (k=6), bge-m3 косинус.
"""
from exp_kernels import p1_body, split, embed, cos, extract_kernels, binom_z, AUTHORS


def own_win(held_vec, own_kvec, other_kvec):
    wins = 0
    for hv in held_vec:
        own = max(cos(hv, k) for k in own_kvec)
        alt = max(cos(hv, k) for k in other_kvec)
        wins += own > alt
    return wins, len(held_vec)


# Аврелий — фиксированный «другой» (k=6)
a_tr, _ = split(p1_body("marcus-aurelius"))
a_kvec = embed(extract_kernels(AUTHORS["marcus-aurelius"], a_tr, k=6))

# Макиавелли — held-out + три стратегии кернелов
m_tr, m_hd = split(p1_body("machiavelli"))
m_hvec = embed([c["text"][:500] for c in m_hd])
print(f"machiavelli: train {len(m_tr)} / held-out {len(m_hd)}\n")

variants = {}
variants["flat-6"] = extract_kernels(AUTHORS["machiavelli"], m_tr, k=6)
variants["flat-12"] = extract_kernels(AUTHORS["machiavelli"], m_tr, k=12)
by_src = {}
for c in m_tr:
    by_src.setdefault(c["source"], []).append(c)
ps = []
for src, chs in by_src.items():
    ks = extract_kernels(AUTHORS["machiavelli"], chs, k=6)
    print(f"  per-source [{src}]: {len(ks)} кернелов")
    ps += ks
variants["per-source"] = ps

print("\n=== own>aurelius (held-out Макиавелли ближе к СВОИМ кернелам) ===")
for name, ks in variants.items():
    w, n = own_win(m_hvec, embed(ks), a_kvec)
    z, p = binom_z(w, n)
    print(f"  {name:11} ({len(ks):>2} кернелов): {w}/{n} = {p:.1%}  z={z:+.2f}")
