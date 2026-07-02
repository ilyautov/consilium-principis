#!/usr/bin/env python3
"""§3.2 moat-v2: per-advisor автокалибровка порогов при сборке.

Проблема: abstain_threshold=0.50 и полоса судьи [0.45, 0.65] откалиброваны на ДВУХ
советниках (Machiavelli/Marcus); новый корпус (Сунь-Цзы: 92 стиха + 3505 строк
комментария) даёт другое распределение косинусов → глобальные дефолты либо режут
отвечаемое, либо пропускают камуфляж.

Метод (мини-golden без LLM, детерминирован сидом):
  • answerable-прóбы — сэмпл предложений из чанков корпуса; скор пробы = max косинус
    по НЕ-содержащим её чанкам (self-hit отбрасываем: verbatim-проба к самой себе ≈ 1.0
    и завысила бы answerable-распределение против реальных парафраз-вопросов);
  • OOC — фиксированный камуфляж-набор scripts/moat_battery/<slug>.camouflage.jsonl
    (свой для советника) + generic.camouflage.jsonl (дальний OOC — без него youden
    выберет порог по одному лишь камуфляж-потолку);
  • abstain_threshold = best_operating_point (max youden, тай-брейк ниже false_abstain,
    затем ниже порог) на abstention_curve;
  • ПРАВИЛО ПОЛОСЫ (документируемое): band_lo = threshold − 0.05 (sub-band уже накрыт
    полом abstention, зеркало глобальной пары 0.50/0.45); band_hi = max(камуфляжных
    OOC-скоров) + 0.05 (камуфляж-потолок + запас — та же логика, которой выбран
    глобальный 0.65 поверх наблюдённого потолка 0.612), кап 0.95.

Куда пишется: advisors/<slug>/build/calibration.json (артефакт сборки, гитигнор —
как kernels.json). Резолюция per-advisor → глобальный фоллбэк:
  • engine.load_backend_threshold читает calibration.json ПЕРЕД board_config;
  • relevance_gate._gate_config оверлеит band_lo/band_hi из calibration.json;
  • doctor показывает флаг calibrated per советник (нет файла = false, глоб. дефолты).

Требует semantic-тира (ollama+bge-m3). Нет → честный skip: файл НЕ пишется,
calibrated=false в doctor, глобальные дефолты продолжают действовать.
"""
import json
import hashlib
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

BATTERY_DIR = os.path.join(HERE, "moat_battery")
LO_MARGIN = 0.05          # band_lo = threshold − LO_MARGIN (зеркало глобальных 0.50→0.45)
HI_MARGIN = 0.05          # band_hi = max(camouflage OOC) + HI_MARGIN (потолок + запас)
HI_CAP = 0.95
N_ANS_DEFAULT = 24
MIN_SCORES = 6            # меньше проб/OOC → калибровка не имеет опоры (skip)


# ───────────────────────── чистая математика (оффлайн-тестируемая) ───────────

def band_rule(threshold, camouflage_ooc_scores, lo_margin=LO_MARGIN,
              hi_margin=HI_MARGIN, hi_cap=HI_CAP):
    """(band_lo, band_hi) по документированному правилу (см. модульный докстринг).
    camouflage_ooc_scores — скоры ИМЕННО камуфляжных OOC (generic в потолок не входит:
    полоса существует ради зоны пересечения камуфляжа с отвечаемым)."""
    if not camouflage_ooc_scores:
        raise ValueError("нет камуфляжных OOC-скоров — потолок полосы не определён")
    lo = max(0.0, round(threshold - lo_margin, 3))
    hi = min(hi_cap, round(max(camouflage_ooc_scores) + hi_margin, 3))
    return lo, hi


def compute_calibration(ooc_scores, ans_scores, camouflage_scores=None, n_points=41):
    """Чистый расчёт калибровки из уже собранных скоров.

    ooc_scores — ВСЕ OOC (камуфляж + generic), ans_scores — answerable-прóбы,
    camouflage_scores — подмножество ooc для потолка полосы (None → ooc целиком).
    Возврат {"valid", "abstain_threshold", "band_lo", "band_hi", "auc", "best"} или
    {"valid": False, "reason"} на вырожденных данных (fail-closed: НЕ калибруем)."""
    from abstention_curve import (curve_from_scores, best_operating_point,
                                  thresholds_from_scores, curve_auc)
    if len(ooc_scores) < MIN_SCORES or len(ans_scores) < MIN_SCORES:
        return {"valid": False,
                "reason": f"мало данных (ooc={len(ooc_scores)}, ans={len(ans_scores)}, "
                          f"нужно ≥{MIN_SCORES} каждых)"}
    pts = curve_from_scores(ooc_scores, ans_scores,
                            thresholds_from_scores(ooc_scores + ans_scores, n=n_points))
    best = best_operating_point(pts)
    if best is None or best["youden"] <= 0:
        return {"valid": False, "reason": "наборы неразделимы (youden <= 0) — "
                                          "порог не имеет рабочей точки"}
    t = round(best["threshold"], 4)
    lo, hi = band_rule(t, camouflage_scores if camouflage_scores else ooc_scores)
    if not lo < hi:
        return {"valid": False, "reason": f"полоса выродилась (lo={lo} >= hi={hi})"}
    return {"valid": True, "abstain_threshold": t, "band_lo": lo, "band_hi": hi,
            "auc": round(curve_auc(ooc_scores, ans_scores), 4),
            "best": {k: round(v, 4) for k, v in best.items()}}


# ───────────────────────── мини-golden ───────────────────────────────────────

def sample_answerable_probes(advisor_dir, n=N_ANS_DEFAULT, seed=0, min_chunk=200):
    """Детерминированный (seed) сэмпл предложений-проб из чанков корпуса.
    Возврат [{"q": sentence, "chunk": full_chunk_text}] — chunk нужен, чтобы при
    скоринге отбросить self-hit."""
    from corpusbuild.paths import corpus_path
    cp = corpus_path(advisor_dir)
    if not os.path.isfile(cp):
        return []
    chunks = []
    with open(cp, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line).get("text", "")
            except Exception:
                continue
            if len(t) >= min_chunk:
                chunks.append(t)
    rng = random.Random(seed)
    rng.shuffle(chunks)
    probes = []
    for t in chunks:
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t)]
        cand = [s for s in sents if 40 <= len(s) <= 220]
        if not cand:
            continue
        probes.append({"q": max(cand, key=len), "chunk": t})
        if len(probes) >= n:
            break
    return probes


def load_smoke_ooc(advisor_dir):
    """(camouflage_rows, generic_rows): свой камуфляж-набор советника из
    moat_battery (по slug) — БЕЗ фоллбэка на чужой; generic — всегда."""
    slug = os.path.basename(os.path.abspath(advisor_dir).rstrip("/"))
    def _load(name):
        p = os.path.join(BATTERY_DIR, name)
        if not os.path.isfile(p):
            return []
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    return _load(f"{slug}.camouflage.jsonl"), _load("generic.camouflage.jsonl")


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def collect_scores(advisor_dir, probes, ooc_rows, retrieve_fn=None, top_k=5):
    """Скоры для кривой. answerable-проба: max скор по хитам, НЕ содержащим пробу
    (self-hit отброшен — см. модульный докстринг); все хиты self → проба пропущена.
    OOC: max скор как есть. retrieve_fn — TEST SEAM (прод = eval.retrieve)."""
    if retrieve_fn is None:
        from eval import retrieve as retrieve_fn
    ans_scores = []
    for p in probes:
        hits = retrieve_fn(p["q"], advisor_dir, top_k)
        nq = _norm(p["q"])
        ext = [h["score"] for h in hits if nq not in _norm(h.get("text", ""))]
        if ext:
            ans_scores.append(max(ext))
    ooc_scores = []
    for row in ooc_rows:
        hits = retrieve_fn(row["q"], advisor_dir, top_k)
        ooc_scores.append(max((h["score"] for h in hits), default=0.0))
    return ooc_scores, ans_scores


# ───────────────────────── файл калибровки + оркестрация ─────────────────────

def calibration_file(advisor_dir):
    from corpusbuild.paths import build_dir
    return os.path.join(build_dir(advisor_dir), "calibration.json")


def _corpus_sha256(advisor_dir):
    from corpusbuild.paths import corpus_path
    try:
        with open(corpus_path(advisor_dir), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def write_calibration(advisor_dir, result):
    p = calibration_file(advisor_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return p


def calibrate(advisor_dir, n_ans=N_ANS_DEFAULT, seed=0, retrieve_fn=None, write=True):
    """Полный шаг калибровки. Возврат = содержимое calibration.json при успехе,
    {"calibrated": False, "reason"} при skip (файл при skip НЕ пишется — глобальные
    дефолты продолжают действовать, doctor показывает честное «не калиброван»)."""
    import relevance_gate
    if retrieve_fn is None and not relevance_gate.is_semantic(advisor_dir):
        return {"calibrated": False,
                "reason": "semantic-тир недоступен (нужны ollama+bge-m3) — "
                          "глобальные дефолты остаются"}
    camo, generic = load_smoke_ooc(advisor_dir)
    if not camo:
        slug = os.path.basename(os.path.abspath(advisor_dir).rstrip("/"))
        return {"calibrated": False,
                "reason": f"нет камуфляж-набора scripts/moat_battery/{slug}.camouflage.jsonl "
                          "— потолок полосы не измерить"}
    probes = sample_answerable_probes(advisor_dir, n=n_ans, seed=seed)
    ooc_rows = camo + generic
    ooc_scores, ans_scores = collect_scores(advisor_dir, probes, ooc_rows,
                                            retrieve_fn=retrieve_fn)
    camo_scores = ooc_scores[:len(camo)]
    comp = compute_calibration(ooc_scores, ans_scores, camouflage_scores=camo_scores)
    if not comp.get("valid"):
        return {"calibrated": False, "reason": comp.get("reason", "расчёт не удался")}
    import relevance_gate as rg
    from engine.semantic import SemanticEngine
    result = {
        "calibrated": True,
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": "semantic",
        "seed": seed,
        "abstain_threshold": {"semantic": comp["abstain_threshold"]},
        "relevance_gate": {"band_lo": comp["band_lo"], "band_hi": comp["band_hi"]},
        "rule": (f"threshold = best_operating_point (max youden); band_lo = threshold - "
                 f"{LO_MARGIN}; band_hi = max(camouflage OOC) + {HI_MARGIN}, cap {HI_CAP}"),
        # Честная оговорка метода: answerable-прóбы (verbatim-предложения корпуса, даже с
        # отброшенным self-hit) скорят ВЫШЕ реальных парафраз-вопросов → порог фактически
        # садится чуть выше камуфляж-потолка. Направление ошибки fail-closed (лишний 🟡,
        # не ложный 🔵); замер на живом Machiavelli: probe-порог 0.598 vs валидированный
        # golden-порог 0.50 при потолке 0.595.
        "caveat": ("probe-based: answerable-прóбы смещены вверх против парафраз-вопросов; "
                   "порог ~= камуфляж-потолок + ε, ошибка в fail-closed сторону"),
        "data": {"n_ans": len(ans_scores), "n_ooc": len(ooc_scores),
                 "n_camouflage": len(camo), "auc": comp["auc"], "best": comp["best"],
                 "camouflage_ceiling": round(max(camo_scores), 4) if camo_scores else None,
                 "ans_min": round(min(ans_scores), 4), "ans_max": round(max(ans_scores), 4)},
        "defaults": {"abstain_threshold": SemanticEngine.DEFAULT_THRESHOLD,
                     "band_lo": rg.BAND_LO, "band_hi": rg.BAND_HI},
        "corpus_sha256": _corpus_sha256(advisor_dir),
    }
    if write:
        write_calibration(advisor_dir, result)
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Per-advisor автокалибровка abstain_threshold и полосы судьи (§3.2)")
    ap.add_argument("advisors", nargs="+", help="папки советников (advisors/sun-tzu …)")
    ap.add_argument("--n-ans", type=int, default=N_ANS_DEFAULT)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="посчитать, не писать файл")
    args = ap.parse_args()
    rc = 0
    for adv in args.advisors:
        print(f"\n=== {adv} ===")
        r = calibrate(adv, n_ans=args.n_ans, seed=args.seed, write=not args.dry_run)
        if not r.get("calibrated"):
            print(f"  SKIP: {r['reason']}")
            rc = 1
            continue
        d = r["data"]
        print(f"  abstain_threshold(semantic) = {r['abstain_threshold']['semantic']}"
              f"  (глоб. {r['defaults']['abstain_threshold']})")
        print(f"  полоса судьи = [{r['relevance_gate']['band_lo']}, "
              f"{r['relevance_gate']['band_hi']}]"
              f"  (глоб. [{r['defaults']['band_lo']}, {r['defaults']['band_hi']}])")
        print(f"  auc={d['auc']}  youden={d['best']['youden']}  "
              f"камуфляж-потолок={d['camouflage_ceiling']}  "
              f"n_ans={d['n_ans']} n_ooc={d['n_ooc']}")
        if not args.dry_run:
            print(f"  → {calibration_file(adv)}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
