#!/usr/bin/env python3
"""serving_gate_eval.py — eval серверной поверхности Consilium-Principis MCP.

Мерит ДВЕ вещи на ДЕТЕРМИНИРОВАННОЙ стороне сервера (что он отдаёт хосту):

  1. cite_misapplication_rate  — как часто cite() выдаёт хосту grounded (🔵/🟢) материал
     на камуфляжных OOC-вопросах. Высокая rate → сервер ставит хоста в ситуацию misapplication
     (истинная 🔵-цитата применена к вопросу, который она не отвечает; ошибка на уровне хоста,
     не сервера — но сервер её провоцирует).

  2. judge_gate_efficacy  — LLM-judge-гейт (relevance_judge.judge 0-3) над пассажами retrieve:
     хорошо ли разделяет OOC (должен гейтить) vs answerable (должен пропускать)?

  3. cosine_false_accept_rate  — baseline: как часто max(retrieve.score) >= 0.50 на тех же OOC?
     Headline: cosine false_accept vs judge false_accept на одних вопросах.

CLI gated on llm_local.available() + наличие корпуса. Seams (cite_fn/retrieve_fn/judge_fn)
инжектируются в тестах — все тесты офлайн.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────── 1. cite-misapplication ─────────────────────────────

def cite_misapplication_rate(advisor_dir, ooc_questions, cite_fn=None):
    """Fraction of OOC questions for which cite() hands the host grounded quotes.

    Args:
        advisor_dir: путь к папке советника
        ooc_questions: list of {"q": ..., "why": ...}
        cite_fn: callable(advisor_dir, query) -> {"quotes": [{text,source,marker}, ...], ...}
                 TEST SEAM — default: mcp_server._cite

    Returns:
        {
            "rate": float,       # fraction of OOC q's with >= 1 grounded quote (higher = worse)
            "n": int,            # total OOC questions evaluated
            "per_q": [           # per-question detail
                {"q": str, "n_grounded": int, "markers": [str]}
            ]
        }
    """
    if cite_fn is None:
        from mcp_server import _cite as _default_cite
        cite_fn = _default_cite

    per_q = []
    grounded_count = 0
    for item in ooc_questions:
        q = item["q"]
        result = cite_fn(advisor_dir, q)
        quotes = result.get("quotes", [])
        grounded_quotes = [qt for qt in quotes if qt.get("marker") in ("🔵", "🟢")]
        n_grounded = len(grounded_quotes)
        markers = [qt.get("marker") for qt in grounded_quotes]
        if n_grounded >= 1:
            grounded_count += 1
        per_q.append({"q": q, "n_grounded": n_grounded, "markers": markers})

    n = len(ooc_questions)
    return {
        "rate": round(grounded_count / n, 4) if n > 0 else 0.0,
        "n": n,
        "per_q": per_q,
    }


# ───────────────────────── 2. judge-gate efficacy ─────────────────────────────

def judge_gate_efficacy(advisor_dir, ooc_questions, answerable_questions,
                        retrieve_fn=None, judge_fn=None, top_k=3, rel_threshold=2,
                        n_samples=1):
    """Measures how well an LLM-judge gate separates OOC from answerable questions.

    For each question: retrieve top_k passages, judge each, take max_judge.
    Decision = PASS if max_judge >= rel_threshold, else GATE.

    Args:
        advisor_dir: путь к папке советника
        ooc_questions: list of {"q": ...} (or {"q":..., "why":...})
        answerable_questions: list of {"q": ..., "anchor": ..., "ref": ...}
        retrieve_fn: callable(query, advisor_dir, top_k) -> [{text, score, source}]
                     TEST SEAM — default: eval.retrieve
        judge_fn: callable(query, passage_text) -> int 0-3
                  TEST SEAM — default: relevance_judge.judge
        top_k: int
        rel_threshold: min judge score to count as "answered" (default 2)
        n_samples: сэмплов судьи на пассаж, рейтинг = МЕДИАНА (идиома
                   poison_eval.inflation_eval): живой судья на границе уровней
                   (1↔2) шумит ±1 в одиночном сэмпле — одиночный флип конфаундит
                   шум с решением гейта (ревью M6: при n=12 флип = 8.3 п.п.).
                   Исключение судьи в сэмпле → 0 (fail-closed: упавшее ≠
                   релевантное). Дефолт 1 = прежнее поведение (детерминированные
                   сеамы в тестах); живые прогоны — n_samples=3.

    Returns:
        {
            "ooc_true_negative_rate": float,    # fraction OOC correctly gated OUT (high = good)
            "ans_true_positive_rate": float,    # fraction answerable passed through (high = good)
            "ooc_false_accept": float,          # 1 - ooc_true_negative_rate (the moat leak)
            "ooc_per_q": [{q, max_judge, decision}],
            "ans_per_q": [{q, max_judge, decision}],
            "n_ooc": int,
            "n_ans": int,
        }
    """
    if retrieve_fn is None:
        from eval import retrieve as _retrieve
        retrieve_fn = _retrieve
    if judge_fn is None:
        from relevance_judge import judge as _judge
        judge_fn = _judge

    def _judge_median(q, passage_text):
        samples = []
        for _ in range(max(1, n_samples)):
            try:
                samples.append(int(judge_fn(q, passage_text)))
            except Exception:
                samples.append(0)                # fail-closed, как в poison_eval
        samples.sort()
        return samples[len(samples) // 2]        # медиана

    def _eval_question(q):
        passages = retrieve_fn(q, advisor_dir, top_k)
        if not passages:
            max_judge = 0
        else:
            max_judge = max(_judge_median(q, p["text"]) for p in passages)
        decision = "PASS" if max_judge >= rel_threshold else "GATE"
        return {"q": q, "max_judge": max_judge, "decision": decision}

    ooc_per_q = [_eval_question(item["q"]) for item in ooc_questions]
    ans_per_q = [_eval_question(item["q"]) for item in answerable_questions]

    n_ooc = len(ooc_per_q)
    n_ans = len(ans_per_q)

    ooc_gated = sum(1 for r in ooc_per_q if r["decision"] == "GATE")
    ooc_tnr = round(ooc_gated / n_ooc, 4) if n_ooc > 0 else 0.0
    ooc_fa  = round(1.0 - ooc_tnr, 4)     if n_ooc > 0 else 0.0

    ans_passed = sum(1 for r in ans_per_q if r["decision"] == "PASS")
    ans_tpr = round(ans_passed / n_ans, 4) if n_ans > 0 else 0.0

    return {
        "ooc_true_negative_rate": ooc_tnr,
        "ans_true_positive_rate": ans_tpr,
        "ooc_false_accept": ooc_fa,
        "ooc_per_q": ooc_per_q,
        "ans_per_q": ans_per_q,
        "n_ooc": n_ooc,
        "n_ans": n_ans,
    }


# ───────────────────────── 3. cosine baseline ─────────────────────────────────

def cosine_false_accept_rate(advisor_dir, ooc_questions, retrieve_fn=None,
                             top_k=3, cosine_threshold=0.50):
    """Baseline: fraction of OOC questions where max retrieval score >= cosine_threshold.

    Args:
        advisor_dir: path to advisor dir
        ooc_questions: list of {"q": ...}
        retrieve_fn: callable(query, advisor_dir, top_k) -> [{text, score, source}]
                     TEST SEAM — default: eval.retrieve
        top_k: int
        cosine_threshold: score threshold (default 0.50 matching abstain_threshold)

    Returns:
        {"false_accept_rate": float, "n": int, "per_q": [{q, max_score, decision}]}
    """
    if retrieve_fn is None:
        from eval import retrieve as _retrieve
        retrieve_fn = _retrieve

    per_q = []
    false_accepts = 0
    for item in ooc_questions:
        q = item["q"]
        passages = retrieve_fn(q, advisor_dir, top_k)
        max_score = max((p.get("score", 0.0) for p in passages), default=0.0)
        decision = "PASS" if max_score >= cosine_threshold else "GATE"
        if decision == "PASS":
            false_accepts += 1
        per_q.append({"q": q, "max_score": round(max_score, 4), "decision": decision})

    n = len(ooc_questions)
    return {
        "false_accept_rate": round(false_accepts / n, 4) if n > 0 else 0.0,
        "n": n,
        "per_q": per_q,
    }


# ───────────────────────── 4. main ────────────────────────────────────────────

def _default_out_path():
    """Дефолт пути вердикта — внутри репо (docs/demo/), не scratchpad в /private/tmp
    (ревью M6: хардкод claude-501-пути делал прогон невоспроизводимым вне этой машины)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "demo", "serving-gate-verdict.md")


def _write_verdict(out_path, lines):
    """Пишет markdown-вердикт; родительские каталоги создаются."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="eval серверной поверхности "
                                             "(cite-misapplication, judge-gate, cosine-baseline)")
    ap.add_argument("--out", default=_default_out_path(),
                    help="куда писать markdown-вердикт "
                         "(дефолт: docs/demo/serving-gate-verdict.md в репо)")
    args = ap.parse_args()

    import llm_local
    if not llm_local.available():
        print("ollama недоступен — реальный прогон невозможен. Проверь: ollama serve")
        return

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    ADVISORS = [
        ("advisors/marcus-aurelius", "Marcus Aurelius", "marcus-aurelius"),
        ("advisors/machiavelli",     "Machiavelli",     "machiavelli"),
    ]

    from synth_eval import gen_adversarial_ooc
    from eval import retrieve as _eval_retrieve, load_golden
    from relevance_judge import judge as _judge
    from mcp_server import _cite
    from corpusbuild.paths import corpus_path

    lines = ["# Serving Gate Eval — Verdict", "",
             "Date: 2026-07-01", ""]

    for rel_adv_dir, author, slug in ADVISORS:
        adv_dir = os.path.join(project_root, rel_adv_dir)
        lines.append(f"## {author} (`{slug}`)")
        lines.append("")

        cp = corpus_path(adv_dir)
        if not os.path.isfile(cp):
            msg = f"ПРОПУСК: нет корпуса ({cp})"
            print(f"  [{slug}] {msg}")
            lines.append(msg); lines.append("")
            continue

        print(f"\n{'='*60}")
        print(f"=== {author} ({slug}) ===")
        print(f"{'='*60}")

        # --- OOC camouflaged questions ---
        print("Генерирую OOC-вопросы (n=12)...")
        try:
            ooc_questions = gen_adversarial_ooc(adv_dir, author, n=12)
        except Exception as e:
            msg = f"ОШИБКА генерации OOC: {e}"
            print(f"  {msg}"); lines.append(msg); lines.append(""); continue

        if not ooc_questions:
            msg = "OOC-вопросы не сгенерировались (LLM вернул пустоту)"
            print(f"  {msg}"); lines.append(msg); lines.append(""); continue
        print(f"  OOC сгенерировано: {len(ooc_questions)}")

        # --- Answerable from golden ---
        golden, _ = load_golden(slug, "retrieval")
        if not golden:
            msg = f"Нет golden retrieval (scripts/golden/{slug}.retrieval.jsonl)"
            print(f"  {msg}"); lines.append(msg); lines.append(""); continue
        answerable = golden[:15]
        print(f"  Answerable (golden): {len(answerable)}")

        # ── 1. cite-misapplication ──
        print("\n[1] cite_misapplication_rate...")
        cite_res = cite_misapplication_rate(adv_dir, ooc_questions, cite_fn=_cite)
        n_misapply = sum(1 for r in cite_res["per_q"] if r["n_grounded"] > 0)
        print(f"  rate={cite_res['rate']:.3f}  misapply={n_misapply}/{cite_res['n']}")
        for row in cite_res["per_q"]:
            if row["n_grounded"] > 0:
                print(f"    MISAPPLY: {row['q'][:70]}  markers={row['markers']}")

        lines += [
            "### 1. cite_misapplication_rate",
            f"- rate = **{cite_res['rate']:.3f}** (n={cite_res['n']})",
            f"- {n_misapply} / {cite_res['n']} OOC вопросов получили grounded цитаты от cite()",
            "",
        ]

        # ── 2. judge-gate ──
        print("\n[2] judge_gate_efficacy (top_k=3, threshold=2)...")
        def _retfn(q, d, k):
            return _eval_retrieve(q, d, top_k=k)

        jg = judge_gate_efficacy(
            adv_dir, ooc_questions, answerable,
            retrieve_fn=_retfn, judge_fn=_judge,
            top_k=3, rel_threshold=2, n_samples=3,
        )
        print(f"  ooc_true_negative_rate = {jg['ooc_true_negative_rate']:.3f}")
        print(f"  ans_true_positive_rate = {jg['ans_true_positive_rate']:.3f}")
        print(f"  ooc_false_accept       = {jg['ooc_false_accept']:.3f}")

        lines += [
            "### 2. judge_gate_efficacy (top_k=3, threshold≥2)",
            f"- ooc_true_negative_rate = **{jg['ooc_true_negative_rate']:.3f}**  (correctly gated OOC — higher is better)",
            f"- ans_true_positive_rate = **{jg['ans_true_positive_rate']:.3f}**  (correctly passed answerable — higher is better)",
            f"- ooc_false_accept       = **{jg['ooc_false_accept']:.3f}**  (moat leak)",
            "",
            "#### OOC per-question:",
        ]
        for row in jg["ooc_per_q"]:
            lines.append(f"- [{row['decision']}] max_judge={row['max_judge']}  `{row['q'][:72]}`")
        lines += ["", "#### Answerable per-question:"]
        for row in jg["ans_per_q"]:
            lines.append(f"- [{row['decision']}] max_judge={row['max_judge']}  `{row['q'][:72]}`")
        lines.append("")

        # ── 3. cosine vs judge ──
        print("\n[3] cosine_false_accept_rate (threshold=0.50)...")
        cos = cosine_false_accept_rate(adv_dir, ooc_questions, retrieve_fn=_retfn, top_k=3)
        rescue = cos["false_accept_rate"] - jg["ooc_false_accept"]
        if rescue > 0.05:
            verdict = "ДА — судья улучшает гейт"
        elif rescue > -0.05:
            verdict = "НЕЙТРАЛЬНО — без заметной разницы"
        else:
            verdict = "НЕТ — судья хуже косинуса (осторожно!)"
        print(f"  cosine false_accept = {cos['false_accept_rate']:.3f}")
        print(f"  judge  false_accept = {jg['ooc_false_accept']:.3f}")
        print(f"  Разница cosine−judge: {rescue:+.3f}  →  {verdict}")

        lines += [
            "### 3. cosine vs judge (на одних OOC-вопросах)",
            "| гейт | false_accept |",
            "|------|-------------|",
            f"| косинус (≥ 0.50) | {cos['false_accept_rate']:.3f} |",
            f"| судья (max_judge ≥ 2) | {jg['ooc_false_accept']:.3f} |",
            f"- Разница cosine−judge: **{rescue:+.3f}**",
            f"- Вердикт: **{verdict}**",
            "",
        ]

    _write_verdict(args.out, lines)
    print(f"\n=== Вердикт записан: {args.out} ===")


if __name__ == "__main__":
    main()
