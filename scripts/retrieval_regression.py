#!/usr/bin/env python3
"""Оффлайн quality-gate: математика метрик из ЗАМОРОЖЕННЫХ скоров + сравнение с baseline.

Спека 2026-07-18 узел 2, Вариант C (гибрид), слой 2. Разделяет ДВЕ регрессии, слитые сегодня:
  • регресс КОДА метрик/порогов — ловится ЗДЕСЬ, оффлайн, на каждый PR (сеть не нужна);
  • регресс движка/индекса — ловится слоем-3 refresh (ритуал владельца на semantic-машине,
    docs/dev/retrieval-regression-refresh.md), где движок реально есть.

Математика метрик — ЧИСТАЯ: на вход замороженные per-question скоры/хиты (продюсер —
eval.py --emit-metrics / refresh-скрипт на живой машине), на выход те же метрики, что печатает
eval (abstention_curve + top-k доли). Поэтому детерминированно тестируется без ollama.

Baseline (docs/dev/retrieval-baseline.json) фиксирует ожидаемые метрики + backend + per-advisor
corpus_sha256. Сравнение честно ТОЛЬКО при совпадении corpus_sha256 (иначе baseline stale —
явный fail, не молчание, как load_calibration/golden drift). degenerate-страты пропускаются
(кросс-язык на lexical даёт недостоверные числа — сравнивать нельзя).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from abstention_curve import curve_auc  # чистая математика разделимости

# Направление «лучше» по метрике: +1 — выше лучше (регресс = падение), -1 — ниже лучше (рост).
METRIC_DIRECTION = {
    "top1": +1, "top3": +1, "honest_abstain": +1, "auc": +1,
    "false_abstain": -1,
}
DEFAULT_TOLERANCE = {
    "top1": 0.05, "top3": 0.05, "honest_abstain": 0.05, "auc": 0.05,
    "false_abstain": 0.05,
}


def _frac_below(scores, t):
    if not scores:
        return 0.0
    return sum(1 for s in scores if s < t) / len(scores)


def metrics_from_frozen(adv_frozen, threshold=0.5):
    """Пересчитать метрики страт из замороженных скоров/хитов ОДНОГО советника.

    adv_frozen = {
      "ooc_scores": [max-скор ретрива по каждому OOC-вопросу],
      "ans_scores": [max-скор по каждому answerable-вопросу],
      "retrieval": {"<lang>": {"hit1": [bool...], "hit3": [bool...], "degenerate": bool?}},
    }
    Возвращает {"ooc": {honest_abstain, false_abstain, auc}, "<lang>": {top1, top3, n, degenerate?}}.
    """
    out = {}
    ooc = adv_frozen.get("ooc_scores") or []
    ans = adv_frozen.get("ans_scores") or []
    if ooc and ans:
        out["ooc"] = {
            "honest_abstain": _frac_below(ooc, threshold),   # OOC < порог → корректный отказ
            "false_abstain": _frac_below(ans, threshold),    # answerable < порог → ЛОЖНЫЙ отказ
            "auc": curve_auc(ooc, ans),
        }
    for lang, r in (adv_frozen.get("retrieval") or {}).items():
        h1 = r.get("hit1") or []
        h3 = r.get("hit3") or []
        n = len(h1)
        st = {
            "top1": (sum(1 for x in h1 if x) / n) if n else 0.0,
            "top3": (sum(1 for x in h3 if x) / n) if n else 0.0,
            "n": n,
        }
        if r.get("degenerate"):
            st["degenerate"] = True
        out[lang] = st
    return out


def _threshold_for(baseline_adv):
    ooc = (baseline_adv.get("strata") or {}).get("ooc") or {}
    return float(ooc.get("threshold", 0.5))


def run_gate(fixture, baseline, tolerance=None, verbose=False):
    """Сравнить пересчитанные из fixture метрики с baseline. → {ok, failures[str]}.

    Fail-условия:
      1. corpus_sha256 фикстуры ≠ baseline у советника → baseline stale, сравнивать нельзя.
      2. метрика ушла ХУЖЕ baseline сверх tolerance (направление по METRIC_DIRECTION).
    degenerate-страты пропускаются (числа недостоверны). Отсутствие страты в baseline — не fail
    (baseline может покрывать подмножество). Пустое пересечение советников — ok (нечего мерить).
    """
    tol = dict(DEFAULT_TOLERANCE)
    tol.update(tolerance or {})
    failures = []
    b_adv = baseline.get("advisors") or {}
    f_adv = fixture.get("advisors") or {}
    for slug, b in b_adv.items():
        f = f_adv.get(slug)
        if f is None:
            continue                                   # фикстура не покрывает — не наша забота здесь
        b_sha = b.get("corpus_sha256")
        f_sha = f.get("corpus_sha256")
        if b_sha and f_sha and b_sha != f_sha:
            failures.append(
                f"{slug}: corpus_sha256 baseline≠fixture (baseline stale: {b_sha}!={f_sha}) — "
                "переснять baseline на текущем корпусе")
            continue                                   # сравнивать метрики бессмысленно
        computed = metrics_from_frozen(f, threshold=_threshold_for(b))
        b_strata = b.get("strata") or {}
        for stratum, b_vals in b_strata.items():
            c_vals = computed.get(stratum)
            if not c_vals:
                continue
            if c_vals.get("degenerate"):
                continue                               # недостоверная страта — пропуск (спека §2.6)
            for metric, direction in METRIC_DIRECTION.items():
                if metric not in b_vals or metric not in c_vals:
                    continue
                base = float(b_vals[metric])
                cur = float(c_vals[metric])
                delta = (cur - base) * direction       # <0 = хуже
                if delta < -tol.get(metric, 0.05):
                    failures.append(
                        f"{slug}/{stratum}/{metric}: {cur:.3f} vs baseline {base:.3f} "
                        f"(регресс {(-delta):.3f} > tol {tol.get(metric, 0.05)})")
    ok = not failures
    if verbose:
        print("GATE:", "PASS" if ok else "FAIL", file=sys.stderr)
        for fl in failures:
            print("  ✗", fl, file=sys.stderr)
    return {"ok": ok, "failures": failures}


def _load(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    """CLI: сверить фикстуру замороженных скоров с baseline. Код возврата 1 при регрессе —
    для использования как блокирующий шаг. Живой retrieve НЕ зовётся (оффлайн)."""
    import argparse
    ap = argparse.ArgumentParser(description="оффлайн regression-гейт retrieval/abstention")
    ap.add_argument("fixture", help="JSON замороженных скоров (tests/fixtures/scores/...)")
    ap.add_argument("baseline", help="JSON baseline (docs/dev/retrieval-baseline.json)")
    args = ap.parse_args(argv)
    res = run_gate(_load(args.fixture), _load(args.baseline), verbose=True)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
