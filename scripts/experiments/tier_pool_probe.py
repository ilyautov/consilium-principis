#!/usr/bin/env python3
"""Изолированный замер тир-осведомлённого ретрива (слой 3 правки #2).

Рантайм НЕ импортирует этот модуль — как antisycophancy_probe/cross_model_probe, это
инструмент, а не часть контура. Ноль правок ранжира: только измеряет.

ЗАЧЕМ. Дип-ресёрч 2026-07-15 (105 агентов) оставил угол «метрики и фальсификация» ПУСТЫМ.
Без него нельзя отличить реальный лифт от подгонки — а два его урока целятся прямо в нас:
  • ClaimTrust: метрика без разрешения (3/200 в обоих режимах) не помешала заключению
    рапортовать «measurable gains» → метрика обязана объявлять свою вырожденность.
  • Airbnb (KDD'20, живые A/B): distribution-matching дал офлайн NDCG +0.03% (нейтрально) и
    статзначимое падение ОНЛАЙН → офлайн-нейтральность не доказывает безвредность.

ДВЕ МЕТРИКИ ВМЕСТЕ (в этом вся соль):
  • blue_share  — доля 🔵-eligible в пуле (КОМПОЗИЦИЯ);
  • anchor_rank — доехал ли ИМЕННО ТОТ P1, что отвечает на вопрос (ПРИГОДНОСТЬ).
Рост share при падении anchor = квота накупила мусорных слотов. Принцип Joachims (KDD'24):
«slot constraints act on the relevant items, not all items» — слот с нерелевантным
кандидатом стоит НОЛЬ. Одна blue_share этого не увидит и соврёт.

АНТИ-ПОДГОНКА. Запросы не выдумываются под правку: golden сделан 23–25 июня, до задачи.
auto.jsonl — ПАРНЫЙ дизайн (literal/abstract на ОДИН якорь, target_tier=P1) → меряет градиент
стиля запроса при фиксированном искомом пассаже. Self-bias снят построением gen_golden:
вопросы генерил LLM, ретрив — bge-m3, разные системы.

Живой прогон: --run (нужен ollama/bge-m3). Офлайн-тесты бьют чистые функции.
"""
import argparse
import datetime
import json
import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
# scripts/experiments НЕ пакет (нет __init__.py) → плоский импорт, как в соседних пробах.
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, HERE)

from golden_meta import split_meta  # noqa: E402  §1.4: _meta-строка ≠ golden-запись

RESULTS_DIR = os.path.join(HERE, "results")
GOLDEN_DIR = os.path.join(_SCRIPTS, "golden")
BLUE_TIERS = ("P1", "P2")
DEFAULT_K = 8          # top_k, которым ходит cite
MIN_N = 8              # ниже — вердикта не даём (underpowered)


def _norm(s):
    """Нормализация как в гейте верности: регистр/пунктуация/пробелы не должны решать."""
    import re
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _text(h):
    return h.get("text", "") if isinstance(h, dict) else getattr(h, "text", "")


def _tier(h):
    return h.get("tier") if isinstance(h, dict) else getattr(h, "tier", None)


def anchor_rank(hits, anchor):
    """1-based ранг пассажа, содержащего якорь, или None. Тот же hit-критерий, что в eval:
    нормализованный anchor ⊂ нормализованный текст."""
    na = _norm(anchor)
    if not na:
        return None
    for i, h in enumerate(hits, 1):
        if na in _norm(_text(h)):
            return i
    return None


def blue_share(hits):
    """Доля 🔵-eligible в пуле. tier=None → НЕ 🔵 (неизвестен = fail-closed): иначе метрика
    льстила бы легаси-индексам без поля."""
    if not hits:
        return 0.0
    return sum(1 for h in hits if _tier(h) in BLUE_TIERS) / len(hits)


def has_blue(hits):
    """Есть ли в пуле хоть один кандидат, физически способный дать 🔵."""
    return any(_tier(h) in BLUE_TIERS for h in hits or [])


def load_golden(slug, kind):
    path = os.path.join(GOLDEN_DIR, f"{slug}.{kind}.jsonl")
    if not os.path.isfile(path):
        return []
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    return split_meta(rows)[1]


def pair_by_anchor(rows):
    """[{anchor, literal, abstract, ...}] — только ПОЛНЫЕ пары. Непарный якорь ломает парную
    статистику, поэтому честно выкидываем, а не достраиваем."""
    by = {}
    for r in rows:
        a = r.get("anchor")
        d = r.get("difficulty")
        if not a or d not in ("literal", "abstract"):
            continue
        slot = by.setdefault(a, {"anchor": a, "source": r.get("source"),
                                 "target_tier": r.get("target_tier")})
        slot[d] = r.get("q")
    return [p for p in by.values() if p.get("literal") and p.get("abstract")]


def summarize(rows, k=DEFAULT_K):
    """rows: [{anchor_rank, blue_share, has_blue}] → метрики + честный флаг вырожденности."""
    n = len(rows)
    if not n:
        return {"n": 0, "degenerate": True, "anchor_recall": None, "anchor_mrr": None,
                "blue_share_mean": None, "citation_ability": None, "k": k}
    ranks = [r["anchor_rank"] for r in rows]
    recall = sum(1 for r in ranks if r is not None and r <= k) / n
    mrr = sum((1.0 / r) if (r is not None and r <= k) else 0.0 for r in ranks) / n
    share = sum(r["blue_share"] for r in rows) / n
    cite_able = sum(1 for r in rows if r["has_blue"]) / n
    # Урок ClaimTrust: если метрика приняла ОДНО значение на всей батарее, она ничего не
    # различает — и сравнение на ней будет враньём. Объявляем это, а не рапортуем «gains».
    degenerate = (len({r["anchor_rank"] for r in rows}) == 1
                  and len({round(r["blue_share"], 6) for r in rows}) == 1)
    return {"n": n, "k": k, "anchor_recall": recall, "anchor_mrr": mrr,
            "blue_share_mean": share, "citation_ability": cite_able,
            "degenerate": degenerate}


def compare(base, treat):
    """Вердикт по паре сводок. Ловит ровно то, на чём горели другие:
    share↑ + anchor↓ = мусорные слоты (Joachims); просадка anchor = налог (Airbnb)."""
    d_recall = (treat["anchor_recall"] or 0) - (base["anchor_recall"] or 0)
    d_mrr = (treat["anchor_mrr"] or 0) - (base["anchor_mrr"] or 0)
    d_share = (treat["blue_share_mean"] or 0) - (base["blue_share_mean"] or 0)
    tax = -d_mrr                      # положительный налог = якорь просел
    underpowered = min(base.get("n", 0), treat.get("n", 0)) < MIN_N
    junk = d_share > 0 and (d_recall < 0 or d_mrr < 0)
    if underpowered:
        verdict = (f"ВЕРДИКТА НЕТ: n<{MIN_N}. Офлайн-нейтральность и так ничего не доказывает "
                   f"(Airbnb: +0.03% NDCG → минус онлайн), а на таком n — тем более.")
    elif junk:
        verdict = ("МУСОРНЫЕ СЛОТЫ: 🔵 в пуле стало больше, а нужный пассаж доезжает ХУЖЕ — "
                   "квота накупила слотов, которые 🔵 не дадут (принцип Joachims: слот с "
                   "нерелевантным кандидатом стоит ноль).")
    elif d_recall > 0 and tax <= 0:
        verdict = "ЧЕСТНЫЙ ЛИФТ: нужный пассаж доезжает чаще, налога на релевантность нет."
    elif tax > 0:
        verdict = (f"ЛИФТ С НАЛОГОМ: якорь просел на {tax:.3f} MRR. Airbnb: одноосевое "
                   f"ограничение «almost always sacrifices relevance» — решать, стоит ли.")
    else:
        verdict = "БЕЗ ИЗМЕНЕНИЙ: разницы не видно."
    return {"d_anchor_recall": d_recall, "d_anchor_mrr": d_mrr, "d_blue_share": d_share,
            "relevance_tax": tax, "junk_slots_suspected": junk,
            "underpowered": underpowered, "verdict": verdict}


# ------------------------------------------------------------------ живой прогон

def measure(slug, queries, retrieve_fn, k=DEFAULT_K):
    """queries: [(q, anchor)] → [{q, anchor, anchor_rank, blue_share, has_blue}]."""
    adv = os.path.join(_SCRIPTS, "..", "advisors", slug)
    out = []
    for q, anchor in queries:
        hits = retrieve_fn(q, adv, k)
        out.append({"q": q, "anchor": anchor, "anchor_rank": anchor_rank(hits, anchor),
                    "blue_share": blue_share(hits), "has_blue": has_blue(hits)})
    return out


def _default_retrieve(q, adv, k):
    import eval as _eval
    return _eval.retrieve(q, adv, top_k=k)


def run_probe(slug, retrieve_fn=None, k=DEFAULT_K):
    """Базовая линия по советнику: парный градиент стиля (auto) + ручные якоря (retrieval.en)."""
    retrieve_fn = retrieve_fn or _default_retrieve
    res = {"slug": slug, "k": k}
    pairs = pair_by_anchor(load_golden(slug, "auto"))
    if pairs:
        for style in ("literal", "abstract"):
            rows = measure(slug, [(p[style], p["anchor"]) for p in pairs], retrieve_fn, k)
            res[style] = summarize(rows, k)
        res["style_gradient"] = compare(res["abstract"], res["literal"])
    hand = [(r["q"], r["anchor"]) for r in load_golden(slug, "retrieval.en") if r.get("anchor")]
    if hand:
        res["hand_en"] = summarize(measure(slug, hand, retrieve_fn, k), k)
    return res


def format_report(res):
    def f(x):
        return "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
    L = [f"\n{'=' * 72}", f"{res['slug']}  (top_k={res['k']})", "=" * 72,
         f"{'набор':16} {'n':>3} {'anchor@k':>9} {'MRR':>7} {'🔵share':>8} {'cite-able':>10} {'вырожд':>7}"]
    for key in ("literal", "abstract", "hand_en"):
        s = res.get(key)
        if s:
            L.append(f"{key:16} {s['n']:>3} {f(s['anchor_recall']):>9} {f(s['anchor_mrr']):>7} "
                     f"{f(s['blue_share_mean']):>8} {f(s['citation_ability']):>10} "
                     f"{'ДА' if s['degenerate'] else 'нет':>7}")
    g = res.get("style_gradient")
    if g:
        L.append(f"\n  градиент стиля (literal против abstract, ПАРНО — один якорь):")
        L.append(f"    Δanchor-recall {g['d_anchor_recall']:+.3f} · ΔMRR {g['d_anchor_mrr']:+.3f} "
                 f"· Δ🔵share {g['d_blue_share']:+.3f}")
        L.append(f"    {g['verdict']}")
    return "\n".join(L)


def write_results(result, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description="Базовая линия тир-осведомлённого ретрива (изолировано)")
    p.add_argument("--run", action="store_true", help="живой прогон (нужен ollama/bge-m3)")
    p.add_argument("--slugs", default="machiavelli,marcus-aurelius,sun-tzu")
    p.add_argument("--top-k", type=int, default=DEFAULT_K)
    a = p.parse_args(argv)
    if not a.run:
        print("Сухой режим. Живой прогон: --run (нужен ollama/bge-m3).")
        print("Меряет: anchor@k (доехал ли НУЖНЫЙ P1) + 🔵share (композиция пула) — вместе,")
        print("потому что share↑ при anchor↓ = мусорные слоты (Joachims), а не победа.")
        return 0
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "top_k": a.top_k, "advisors": []}
    for slug in [s for s in a.slugs.split(",") if s]:
        res = run_probe(slug, k=a.top_k)
        out["advisors"].append(res)
        print(format_report(res))
    stamp = datetime.date.today().isoformat()
    path = write_results(out, os.path.join(RESULTS_DIR, f"tier-pool-{stamp}.json"))
    print(f"\n→ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
