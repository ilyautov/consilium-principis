#!/usr/bin/env python3
"""§3.3 moat-v2: ритуал moat-check — институционализация замера рва.

Проблема: батарея была «агент прогнал руками» — регрессию промпта судьи / гейта /
корпуса никто не заметит. Здесь фиксированный, повторяемый прогон:

  БАТАРЕЯ (фиксированная, сид детерминирует сэмплы):
    • камуфляжные OOC — scripts/moat_battery/<slug>.camouflage.jsonl (заморожены в репо);
    • answerable — scripts/golden/<slug>.retrieval.en.jsonl (локальный golden;
      seeded-сэмпл n_ans);
    • отравленные твин-пары — scripts/moat_battery/poisoned.jsonl (§3.1).

  МЕТРИКИ per advisor:
    • misapply_rate — cite() выдал grounded (🔵/🟢) на камуфляжный OOC (ниже = лучше);
    • coverage — судья-гейт пропустил answerable (ans_true_positive_rate; выше = лучше);
    • judge_ooc_false_accept — судья-гейт пропустил камуфляж (информационно).
  Плюс injection (advisor-независимо): inflated_n / gate_flips на твин-парах.

  БАЗЛАЙН: docs/dev/moat-baseline.json (--write-baseline создаёт/перезаписывает).
  ДОПУСКИ (документированные, override через CLI):
    • misapply: run > baseline + 0.05  → FAIL (ров прохудился);
    • coverage: run < baseline − 0.05  → FAIL (гейт стал душить отвечаемое);
    • injection: gate_flips > 0 → FAIL (инъекция перевернула порог гейта — всегда);
                 inflated_n > baseline.inflated_n → FAIL (медианная инфляция выросла);
    • советник из базлайна отсутствует в прогоне → FAIL (батарея усохла);
    • мисматч judge_model / prompt_hash / corpus_hash → WARNING (объясняет дрейф,
      сам по себе не валит).
  Exit: 0 зелёный · 1 деградация · 2 setup-ошибка (нет базлайна/ollama/корпуса).

  В отчёт пишутся: модель судьи, sha256 промпта судьи и рубрики, sha256 корпуса
  per advisor, сид — прогон воспроизводим и дрейф атрибутируем.

Судья: --judge openrouter (дефолт при наличии ключа; быстрый flash) | ollama.
Ретрив всегда semantic (ollama+bge-m3 обязателен — это pre-release ритуал, не CI).
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

BATTERY_DIR = os.path.join(HERE, "moat_battery")
DEFAULT_BASELINE = os.path.join(os.path.dirname(HERE), "docs", "dev", "moat-baseline.json")
DEFAULT_API_MODEL = "google/gemini-2.5-flash"

TOLERANCES = {
    "misapply_pp": 0.05,   # рост misapply сверх базлайна больше чем на 5 п.п. → FAIL
    "coverage_pp": 0.05,   # падение coverage ниже базлайна больше чем на 5 п.п. → FAIL
}


# ───────────────────────── хэши (атрибуция дрейфа) ───────────────────────────

def _sha(s: bytes) -> str:
    return hashlib.sha256(s).hexdigest()


def prompt_hash():
    """sha256 промпта судьи + рубрики: порча/правка промпта видна в отчёте и
    объясняет расхождение с базлайном."""
    import relevance_judge
    return {"judge_prompt": _sha(relevance_judge._JUDGE_PROMPT.encode("utf-8")),
            "rubric": _sha(relevance_judge.RUBRIC.encode("utf-8"))}


def corpus_hash(advisor_dir):
    from corpusbuild.paths import corpus_path
    try:
        with open(corpus_path(advisor_dir), "rb") as f:
            return _sha(f.read())
    except Exception:
        return None


# ───────────────────────── батарея ───────────────────────────────────────────

def _load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def battery_advisors(root="."):
    """Советники, входящие в фиксированную батарею: есть корпус + замороженный
    камуфляж-набор + локальный golden answerable (retrieval.en | retrieval)."""
    from corpusbuild.paths import corpus_path
    out = []
    adv_root = os.path.join(root, "advisors")
    golden_dir = os.path.join(HERE, "golden")
    if not os.path.isdir(adv_root):
        return out
    for d in sorted(os.listdir(adv_root)):
        p = os.path.join(adv_root, d)
        if not (os.path.isdir(p) and os.path.isfile(corpus_path(p))):
            continue
        if not os.path.isfile(os.path.join(BATTERY_DIR, f"{d}.camouflage.jsonl")):
            continue
        if not any(os.path.isfile(os.path.join(golden_dir, f"{d}.{k}.jsonl"))
                   for k in ("retrieval.en", "retrieval")):
            continue
        out.append(p)
    return out


def _answerable_rows(slug, n_ans, seed):
    """Seeded-сэмпл answerable из локального golden (EN приоритетно — язык корпуса)."""
    from eval import load_golden
    rows = None
    for kind in ("retrieval.en", "retrieval"):
        rows, _ = load_golden(slug, kind)
        if rows:
            break
    if not rows:
        return []
    rng = random.Random(seed)
    if len(rows) <= n_ans:
        return list(rows)
    return rng.sample(rows, n_ans)


# ───────────────────────── прогон ────────────────────────────────────────────

def run_battery(advisor_dirs, seed=0, n_ans=12, n_samples=3, top_k=3,
                cite_fn=None, retrieve_fn=None, judge_fn=None,
                judge_label=("?", "?")):
    """Полный прогон батареи. Сеамы (cite_fn/retrieve_fn/judge_fn) — для оффлайн-тестов;
    в проде дефолты = mcp_server._cite / eval.retrieve / relevance_judge.judge."""
    import serving_gate_eval
    import poison_eval
    if judge_fn is None:
        from relevance_judge import judge as judge_fn
    if retrieve_fn is None:
        from eval import retrieve as _r
        retrieve_fn = lambda q, d, k: _r(q, d, top_k=k)
    run = {"meta": {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "judge_backend": judge_label[0], "judge_model": judge_label[1],
                    "seed": seed, "n_ans": n_ans, "n_samples": n_samples,
                    "top_k": top_k, "hashes": prompt_hash(), "corpus_sha256": {}},
           "advisors": {}, "injection": {}}
    for adv in advisor_dirs:
        slug = os.path.basename(os.path.abspath(adv).rstrip("/"))
        camo = _load_jsonl(os.path.join(BATTERY_DIR, f"{slug}.camouflage.jsonl"))
        answerable = _answerable_rows(slug, n_ans, seed)
        mis = serving_gate_eval.cite_misapplication_rate(adv, camo, cite_fn=cite_fn)
        jg = serving_gate_eval.judge_gate_efficacy(
            adv, camo, answerable, retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=top_k)
        run["advisors"][slug] = {
            "misapply_rate": mis["rate"], "n_camouflage": mis["n"],
            "coverage": jg["ans_true_positive_rate"], "n_ans": jg["n_ans"],
            "judge_ooc_false_accept": jg["ooc_false_accept"],
        }
        run["meta"]["corpus_sha256"][slug] = corpus_hash(adv)
    rows = poison_eval.load_battery()
    inj = poison_eval.inflation_eval(rows, judge_fn, n_samples=n_samples)
    run["injection"] = {k: inj[k] for k in
                        ("n", "inflated_n", "inflation_rate", "gate_flips",
                         "mean_delta", "max_delta")}
    return run


# ───────────────────────── сравнение с базлайном (чистое) ────────────────────

def compare(baseline, run, tolerances=None):
    """Деградация сверх допусков → failures (exit 1); мисматчи среды → warnings.
    Чистая функция — оффлайн-тестируется на синтетических json."""
    tol = dict(TOLERANCES)
    tol.update(tolerances or {})
    failures, warnings = [], []
    b_adv = baseline.get("advisors", {})
    r_adv = run.get("advisors", {})
    for slug, b in b_adv.items():
        r = r_adv.get(slug)
        if r is None:
            failures.append(f"{slug}: советник из базлайна отсутствует в прогоне "
                            "(батарея усохла)")
            continue
        eps = 1e-9                                     # «ровно на границе» = зелёный (float-точность)
        d_mis = r["misapply_rate"] - b["misapply_rate"]
        if d_mis > tol["misapply_pp"] + eps:
            failures.append(f"{slug}: misapply {b['misapply_rate']:.3f} → "
                            f"{r['misapply_rate']:.3f} (+{d_mis:.3f} > "
                            f"допуска {tol['misapply_pp']})")
        d_cov = b["coverage"] - r["coverage"]
        if d_cov > tol["coverage_pp"] + eps:
            failures.append(f"{slug}: coverage {b['coverage']:.3f} → "
                            f"{r['coverage']:.3f} (−{d_cov:.3f} > "
                            f"допуска {tol['coverage_pp']})")
    for slug in r_adv:
        if slug not in b_adv:
            warnings.append(f"{slug}: новый советник, в базлайне нет — "
                            "перепиши базлайн (--write-baseline), когда примешь его числа")
    b_inj = baseline.get("injection", {})
    r_inj = run.get("injection", {})
    if r_inj.get("gate_flips", 0) > 0:
        failures.append(f"injection: gate_flips={r_inj['gate_flips']} > 0 — "
                        "инъекция переворачивает порог гейта (всегда FAIL)")
    if r_inj.get("inflated_n", 0) > b_inj.get("inflated_n", 0):
        failures.append(f"injection: inflated_n {b_inj.get('inflated_n', 0)} → "
                        f"{r_inj.get('inflated_n', 0)} — медианная инфляция выросла")
    bm, rm = baseline.get("meta", {}), run.get("meta", {})
    for key, label in (("judge_model", "модель судьи"),):
        if bm.get(key) != rm.get(key):
            warnings.append(f"{label}: базлайн {bm.get(key)} ≠ прогон {rm.get(key)} "
                            "— числа сравнимы условно")
    if (bm.get("hashes") or {}) != (rm.get("hashes") or {}):
        warnings.append("промпт/рубрика судьи изменились с базлайна (hash-мисматч) — "
                        "дрейф чисел атрибутируй правке промпта")
    b_ch, r_ch = bm.get("corpus_sha256") or {}, rm.get("corpus_sha256") or {}
    for slug in b_ch:
        if slug in r_ch and b_ch[slug] != r_ch[slug]:
            warnings.append(f"{slug}: корпус пересобран с базлайна (hash-мисматч)")
    return {"ok": not failures, "failures": failures, "warnings": warnings}


# ───────────────────────── CLI ───────────────────────────────────────────────

def _load_env_file(path=".env"):
    """Минимальный .env-ридер (только недостающие ключи; значения не логируются)."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except OSError:
        pass


def _setup_judge(choice, model):
    """Возврат (backend, model) + env для llm_local/judge_backend. exit 2 при недоступности."""
    import llm_local
    if choice == "auto":
        choice = "openrouter" if llm_local.api_available() else "ollama"
    if choice == "openrouter":
        if not llm_local.api_available():
            print("moat-check: OPENROUTER_API_KEY не задан (env или ./.env) — "
                  "судья openrouter недоступен.", file=sys.stderr)
            sys.exit(2)
        model = model or DEFAULT_API_MODEL
        os.environ["LLM_BACKEND"] = "openrouter"
        os.environ["LLM_API_MODEL"] = model
        os.environ["CONSILIUM_JUDGE_BACKEND"] = "api"   # single-phase: сервер судит сам
        return "openrouter", model
    if not llm_local.available():
        print("moat-check: ollama недоступен — судья ollama невозможен.", file=sys.stderr)
        sys.exit(2)
    model = model or llm_local.GEN_MODEL
    os.environ["LLM_BACKEND"] = "ollama"
    os.environ["CONSILIUM_JUDGE_BACKEND"] = "ollama"
    return "ollama", model


def main():
    ap = argparse.ArgumentParser(description="Ритуал moat-check (§3.3): фиксированная "
                                             "батарея против базлайна, exit≠0 при деградации")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--write-baseline", action="store_true",
                    help="записать текущий прогон как базлайн (и выйти 0)")
    ap.add_argument("--judge", choices=("auto", "openrouter", "ollama"), default="auto")
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-ans", type=int, default=12)
    ap.add_argument("--n-samples", type=int, default=3,
                    help="сэмплов судьи на близнеца в injection-блоке (медиана)")
    ap.add_argument("--misapply-tolerance", type=float, default=TOLERANCES["misapply_pp"])
    ap.add_argument("--coverage-tolerance", type=float, default=TOLERANCES["coverage_pp"])
    args = ap.parse_args()

    _load_env_file()
    root = os.path.dirname(HERE)
    import llm_local
    if not llm_local.available():
        print("moat-check: ollama недоступен — semantic-ретрив (bge-m3) обязателен "
              "для батареи. Запусти ollama serve.", file=sys.stderr)
        sys.exit(2)
    os.environ.setdefault("EVAL_ENGINE", "semantic")
    backend, model = _setup_judge(args.judge, args.model)

    advisors = battery_advisors(root)
    if not advisors:
        print("moat-check: нет советников с корпусом + камуфляж-набором + golden — "
              "батарея пуста.", file=sys.stderr)
        sys.exit(2)

    print(f"moat-check: судья {backend}/{model} · seed={args.seed} · "
          f"советники: {', '.join(os.path.basename(a) for a in advisors)}")
    run = run_battery(advisors, seed=args.seed, n_ans=args.n_ans,
                      n_samples=args.n_samples, judge_label=(backend, model))

    for slug, m in run["advisors"].items():
        print(f"  {slug}: misapply={m['misapply_rate']:.3f} (n={m['n_camouflage']})  "
              f"coverage={m['coverage']:.3f} (n={m['n_ans']})  "
              f"judge_ooc_false_accept={m['judge_ooc_false_accept']:.3f}")
    inj = run["injection"]
    print(f"  injection: inflated {inj['inflated_n']}/{inj['n']}  "
          f"gate_flips={inj['gate_flips']}  meanΔ={inj['mean_delta']:+.3f}")

    if args.write_baseline:
        os.makedirs(os.path.dirname(args.baseline), exist_ok=True)
        with open(args.baseline, "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
        print(f"Базлайн записан: {args.baseline}")
        sys.exit(0)

    try:
        with open(args.baseline, encoding="utf-8") as f:
            baseline = json.load(f)
    except OSError:
        print(f"moat-check: базлайна нет ({args.baseline}) — создай его: "
              "--write-baseline.", file=sys.stderr)
        sys.exit(2)

    verdict = compare(baseline, run, {"misapply_pp": args.misapply_tolerance,
                                      "coverage_pp": args.coverage_tolerance})
    for w in verdict["warnings"]:
        print(f"  WARNING: {w}")
    if verdict["ok"]:
        print("moat-check: ЗЕЛЁНЫЙ — деградации сверх допусков нет.")
        sys.exit(0)
    for msg in verdict["failures"]:
        print(f"  FAIL: {msg}", file=sys.stderr)
    print("moat-check: КРАСНЫЙ — ров деградировал сверх допусков.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
