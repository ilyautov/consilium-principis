"""Изолированный офлайн-каркас citation-rate eval (ALCE-адаптация).

Рантайм НЕ импортирует этот модуль. Меряет, какая доля покровно-заявленных verbatim-цитат
РЕАЛЬНО проходит наш детерминированный fidelity-гейт (_fidelity_check из mcp_server, который
зовёт engine.fidelity.best_match — точная нормализованная подстрока по чанкам корпуса, офлайн,
без сети/ollama). Это НЕ доказательство рва третьей стороной — это проверка внутренней
консистентности гейта (он не пропускает невериф. как 🔵/🟢) + baseline-контраст с голым LLM.
Статистика (bootstrap-CI) переиспользована из antisycophancy_probe (DRY).
Спека: внутренний дизайн-док (citation rate eval).
"""
import os
import sys
import re
import json
import argparse
import datetime

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
# scripts/experiments НЕ пакет (нет __init__.py) → плоский импорт, как в cross_model_probe.py.
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, HERE)

# DRY: детерминированная статистика переиспользована из соседнего probe.
from antisycophancy_probe import _bootstrap_ci, _mean, SEED, _safe_call  # noqa: E402
# Ground truth: тот же самый протокол-гейт, что и в продакшне (без мока, без переизобретения).
from mcp_server import _fidelity_check  # noqa: E402
from engine.fidelity import MIN_QUOTE_CHARS  # noqa: E402

DEFAULT_BATTERY = os.path.join(HERE, "citation_rate_battery.jsonl")
RESULTS_DIR = os.path.join(HERE, "results")
DEFAULT_ADVISOR_DIR = "advisors/machiavelli"  # реальный тиреный корпус (build/corpus.jsonl, P1 есть)
DEFAULT_MODEL = "google/gemini-2.5-flash"
GEN_TEMPERATURE = 0.0

_VERIFIED_STATUSES = ("🔵", "🟢")


def load_battery(path=DEFAULT_BATTERY):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ───────────────────────── офлайн-ядро: гейт как ground truth ─────────────────────────

def score_claims(claims):
    """claims: [{"advisor_dir", "quote", "purported_verbatim": bool}, ...]

    citation_precision = verified(🔵/🟢) / count(purported_verbatim=True) — доля цитат,
      заявленных как дословные, которые РЕАЛЬНО проходят гейт. Цель гейта = 1.0 (fail-closed).
    fabrication_rate = 1 - precision.
    abstention_correct = среди purported_verbatim=False (честно не заявленных verbatim) —
      доля, где гейт согласен и возвращает 🟡 (не пропускает как верифицированную).
    precision_ci = bootstrap-CI по индикатору verified на purported_verbatim=True подмножестве.
    """
    scored = []
    for c in claims:
        fc = _fidelity_check(c["quote"], c["advisor_dir"])
        verified = fc["status"] in _VERIFIED_STATUSES
        scored.append({**c, "status": fc["status"], "source": fc.get("source", ""), "verified": verified})

    purported_true = [s for s in scored if s["purported_verbatim"]]
    purported_false = [s for s in scored if not s["purported_verbatim"]]

    n_verified = sum(1 for s in purported_true if s["verified"])
    precision = (n_verified / len(purported_true)) if purported_true else None
    fabrication_rate = (1.0 - precision) if precision is not None else None

    n_abstained = sum(1 for s in purported_false if s["status"] == "🟡")
    abstention_correct = (n_abstained / len(purported_false)) if purported_false else None

    verified_indicators = [1.0 if s["verified"] else 0.0 for s in purported_true]
    precision_ci = _bootstrap_ci(verified_indicators)

    return {
        "n_claims": len(scored),
        "n_purported_verbatim": len(purported_true),
        "n_verified": n_verified,
        "citation_precision": precision,
        "fabrication_rate": fabrication_rate,
        "precision_ci": precision_ci,
        "n_purported_fabricated_or_out": len(purported_false),
        "n_abstained_correct": n_abstained,
        "abstention_correct": abstention_correct,
        "scored": scored,
    }


# ───────────────────────── извлечение заявленных цитат из свободного текста ─────────────────────────

_QUOTE_PATTERNS = (
    re.compile(r"«([^«»]{%d,400})»" % MIN_QUOTE_CHARS),
    re.compile(r"[“\"]([^“”\"]{%d,400})[”\"]" % MIN_QUOTE_CHARS),
)


def extract_quote_claims(text, advisor_dir):
    """Текст ответа (LLM) → список claim-ов с purported_verbatim=True: всё, что автор
    ЗАЯВИЛ в кавычках, покровно претендует на дословность — это и проверяем гейтом."""
    if not text:
        return []
    claims = []
    seen = set()
    for pat in _QUOTE_PATTERNS:
        for m in pat.finditer(text):
            q = m.group(1).strip()
            if len(q) >= MIN_QUOTE_CHARS and q not in seen:
                seen.add(q)
                claims.append({"advisor_dir": advisor_dir, "quote": q, "purported_verbatim": True})
    return claims


# ───────────────────────── живой прогон (--run, нужен ключ) ─────────────────────────

_COUNCIL_PROMPT = """\
Ты советник Макиавелли, отвечающий на вопрос пользователя одним абзацем. Если уместно — приведи
ДОСЛОВНУЮ цитату из «Государя»/«Рассуждений», заключив её в кавычки «...». Если дословной цитаты
нет под рукой — НЕ выдумывай, ответь без цитаты (честное воздержание лучше фабрикации).
Вопрос: <<Q>>"""

_BARE_PROMPT = """\
Ответь на вопрос пользователя как эксперт, одним абзацем. Если уместно — приведи цитату в
кавычках «...», подкрепляющую ответ.
Вопрос: <<Q>>"""


def _model_name():
    return os.getenv("LLM_API_MODEL", DEFAULT_MODEL)


def _default_call(prompt):
    import llm_local
    return llm_local.generate(prompt, model=_model_name(), temperature=GEN_TEMPERATURE)


def _api_available():
    import llm_local
    return llm_local.api_available()


def run_council(battery=None, call=None, advisor_dir=DEFAULT_ADVISOR_DIR):
    """Генерирует ответы 'нашего контура' (совет Макиавелли) и извлекает заявленные цитаты.
    Возвращает (rows, claims): rows несут per-вопрос n_verified для question-level abstention."""
    if battery is None:
        battery = load_battery()
    if call is None:
        call = _default_call
    rows, claims = [], []
    for s in battery:
        prompt = _COUNCIL_PROMPT.replace("<<Q>>", s["question"])
        answer = _safe_call(call, prompt)
        row_claims = extract_quote_claims(answer, advisor_dir)
        n_verified = sum(1 for c in row_claims if _fidelity_check(c["quote"], c["advisor_dir"])["status"]
                          in _VERIFIED_STATUSES)
        rows.append({"id": s["id"], "coverage": s.get("coverage"), "question": s["question"],
                     "answer": answer, "n_quotes": len(row_claims), "n_verified": n_verified})
        claims.extend(row_claims)
    return rows, claims


def run_bare_baseline(battery=None, call=None, advisor_dir=DEFAULT_ADVISOR_DIR):
    """Тот же вопрос голому LLM (без нашего контура/персоны) — baseline-контраст фабрикации."""
    if battery is None:
        battery = load_battery()
    if call is None:
        call = _default_call
    rows, claims = [], []
    for s in battery:
        prompt = _BARE_PROMPT.replace("<<Q>>", s["question"])
        answer = _safe_call(call, prompt)
        row_claims = extract_quote_claims(answer, advisor_dir)
        rows.append({"id": s["id"], "coverage": s.get("coverage"), "question": s["question"],
                     "answer": answer, "n_quotes": len(row_claims)})
        claims.extend(row_claims)
    return rows, claims


def question_level_abstention(rows):
    """Среди out_of_corpus вопросов — доля, где совет НЕ выдал ни одной верифицированной
    цитаты (честное воздержание вместо фабрикации, отмеченной как достоверная)."""
    oos = [r for r in rows if r.get("coverage") == "out_of_corpus"]
    if not oos:
        return None
    correct = sum(1 for r in oos if r.get("n_verified", 0) == 0)
    return correct / len(oos)


def write_results(result, path):
    payload = {"result": result, "model": _model_name(), "seed": SEED,
               "battery": os.path.basename(DEFAULT_BATTERY)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def format_table(result):
    def fmt(x):
        return "  —" if x is None else f"{x:.3f}"

    lines = ["=== Citation-rate eval (ALCE-адаптация) ===",
              f"{'метрика':<28}{'совет':>12}{'голый LLM':>12}"]
    council = result.get("council", {})
    bare = result.get("bare_baseline", {})
    rows = [
        ("citation precision (точность)", "citation_precision"),
        ("fabrication rate (фабрикация)", "fabrication_rate"),
        ("abstention correct (воздержание)", "abstention_correct"),
    ]
    for label, key in rows:
        lines.append(f"{label:<28}{fmt(council.get(key)):>12}{fmt(bare.get(key)):>12}")
    ci = council.get("precision_ci")
    if ci is not None:
        lines.append(f"precision CI95 (совет): [{ci[0]:+.3f}, {ci[1]:+.3f}]")
    qar = result.get("question_abstention_rate")
    if qar is not None:
        lines.append(f"question-level abstention (вне-корпусные вопросы): {qar:.3f}")
    lines.append(f"n_questions={result.get('n_questions')}")
    return "\n".join(lines)


def _run_live():
    battery = load_battery()
    council_rows, council_claims = run_council(battery)
    bare_rows, bare_claims = run_bare_baseline(battery)
    result = {
        "council": score_claims(council_claims),
        "bare_baseline": score_claims(bare_claims),
        "question_abstention_rate": question_level_abstention(council_rows),
        "n_questions": len(battery),
    }
    stamp = datetime.date.today().isoformat()
    write_results(result, os.path.join(RESULTS_DIR, f"citation-rate-{stamp}.json"))
    print(format_table(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Citation-rate eval (ALCE-адаптация, изолировано)")
    parser.add_argument("--run", action="store_true", help="живой прогон через OpenRouter (нужен ключ)")
    args = parser.parse_args(argv)
    if args.run:
        if not _api_available():
            print("Нет OPENROUTER_API_KEY — живой прогон невозможен. Задай ключ в .env и "
                  "LLM_BACKEND=openrouter, LLM_API_MODEL=<модель>.")
            return 1
        os.environ["LLM_BACKEND"] = "openrouter"
        os.environ.setdefault("LLM_API_MODEL", DEFAULT_MODEL)
        return _run_live()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
