"""TDD тесты для scripts/adversarial_loop.py — ВСЕ offline (fake gen_fn / score_fn, без ollama).

Покрываемые инварианты:
  1. Recursion seed-growth: seeds растут раундами; round-2 получает seed_failures из round-1 NEAR/BREACH.
  2. Breach stop: score >= threshold → остановка, stopped_reason=="breach", breached==True.
  3. Dry stop: только SAFE → остановка после dry_rounds сухих раундов, stopped_reason=="dry".
  4. Trajectory + hardest: hardest — top-5 по score; max_ooc_score корректен.
  5. Edge: пустой gen_fn (возвращает []) не роняет луп.
  6. Max_rounds: если нет breach и dry_rounds не достигнуты — останавливаемся по max_rounds.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

from adversarial_loop import harden  # noqa: E402

ADVISOR = "advisors/test-advisor"
AUTHOR  = "Test Author"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_gen(questions_per_round, capture_calls=None):
    """Фабрика fake gen_fn.

    questions_per_round: list[list[{"q","why"}]] — что вернуть на каждый вызов.
    capture_calls: если передан (list), туда пишется {"advisor_dir","author","n","seed_failures"}
    за каждый вызов.
    """
    calls = [list(qs) for qs in questions_per_round]
    idx = [0]

    def gen_fn(advisor_dir, author, n, seed_failures=None):
        if capture_calls is not None:
            capture_calls.append({
                "advisor_dir": advisor_dir,
                "author": author,
                "n": n,
                "seed_failures": list(seed_failures) if seed_failures else None,
            })
        if idx[0] >= len(calls):
            return []
        result = calls[idx[0]]
        idx[0] += 1
        return result

    return gen_fn


def _const_score(value):
    """fake score_fn: всегда возвращает value."""
    def score_fn(q, adv_dir):
        return value
    return score_fn


def _score_by_q(mapping, default=0.0):
    """fake score_fn: score берётся из словаря {q: score}, иначе default."""
    def score_fn(q, adv_dir):
        return mapping.get(q, default)
    return score_fn


# ─── 1. Recursion seed-growth ─────────────────────────────────────────────────

def test_seed_grows_with_near_questions():
    """NEAR-вопросы из round-1 передаются как seed_failures в round-2."""
    THRESHOLD = 0.50
    NEAR_EPS  = 0.05

    # round-1: q_near (score=0.47 → NEAR), q_safe (score=0.30 → SAFE)
    # round-2: любые — нас интересует только то, ЧТО получил gen_fn
    q_near = {"q": "q_near", "why": "near question"}
    q_safe = {"q": "q_safe", "why": "safe question"}

    calls = []
    gen = _make_gen([[q_near, q_safe], [{"q": "q2", "why": ""}]], capture_calls=calls)

    # score: q_near=0.47 (NEAR), q_safe=0.30 (SAFE)
    score_map = {"q_near": 0.47, "q_safe": 0.30, "q2": 0.30}
    score_fn  = _score_by_q(score_map, default=0.30)

    harden(
        ADVISOR, AUTHOR, gen, score_fn,
        threshold=THRESHOLD,
        max_rounds=2,
        n_per_round=2,
        near_eps=NEAR_EPS,
        dry_rounds=10,   # не даём сухому останову прервать
        seed=0,
    )

    assert len(calls) >= 2, "gen_fn должна быть вызвана как минимум дважды"
    round1_call = calls[0]
    round2_call = calls[1]

    # round-1: seed_failures=None (первый раунд — семян нет)
    assert round1_call["seed_failures"] is None, (
        f"round-1 должен получить seed_failures=None, got {round1_call['seed_failures']}"
    )

    # round-2: seed_failures содержит q_near (т.к. он NEAR в round-1)
    sf2 = round2_call["seed_failures"]
    assert sf2 is not None, "round-2 должен получить непустой seed_failures"
    sf2_qs = [s["q"] for s in sf2]
    assert "q_near" in sf2_qs, (
        f"round-2 seed_failures должны содержать q_near, got {sf2_qs}"
    )
    # q_safe (SAFE) не должен попасть в seeds
    assert "q_safe" not in sf2_qs, (
        f"SAFE-вопрос не должен попасть в seeds, но попал: {sf2_qs}"
    )


def test_seed_accumulates_across_rounds():
    """Seeds аккумулируются: round-3 получает NEAR из round-1 И round-2."""
    q_near1 = {"q": "qn1", "why": "near1"}
    q_near2 = {"q": "qn2", "why": "near2"}
    q_safe  = {"q": "qs",  "why": "safe"}

    calls = []
    gen = _make_gen(
        [[q_near1, q_safe], [q_near2, q_safe], [q_safe]],
        capture_calls=calls,
    )
    # near boundary: 0.50 - 0.05 = 0.45
    score_map = {"qn1": 0.46, "qn2": 0.47, "qs": 0.30}
    score_fn  = _score_by_q(score_map, default=0.30)

    harden(
        ADVISOR, AUTHOR, gen, score_fn,
        threshold=0.50, max_rounds=3, n_per_round=2, near_eps=0.05,
        dry_rounds=10, seed=0,
    )

    assert len(calls) >= 3
    sf3 = calls[2]["seed_failures"]
    assert sf3 is not None
    sf3_qs = {s["q"] for s in sf3}
    assert "qn1" in sf3_qs, f"qn1 (NEAR round-1) должен быть в seeds round-3: {sf3_qs}"
    assert "qn2" in sf3_qs, f"qn2 (NEAR round-2) должен быть в seeds round-3: {sf3_qs}"


# ─── 2. Breach stop ───────────────────────────────────────────────────────────

def test_breach_stops_loop():
    """score >= threshold → остановка, breached=True, stopped_reason='breach'."""
    q_breach = {"q": "q_breach", "why": "will breach"}
    gen = _make_gen([[q_breach], [{"q": "q2", "why": ""}]])

    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.55),
        threshold=0.50, max_rounds=5, n_per_round=1, near_eps=0.05,
        dry_rounds=2, seed=0,
    )

    assert result["breached"] is True, "breached должен быть True"
    assert result["stopped_reason"] == "breach", (
        f"stopped_reason=='breach' ожидался, got '{result['stopped_reason']}'"
    )
    # только один раунд должен был выполниться
    assert len(result["rounds"]) == 1
    # нарушающий вопрос должен быть в round.breaches
    assert result["rounds"][0]["n_breach"] == 1
    breach_qs = [b["q"] for b in result["rounds"][0]["breaches"]]
    assert "q_breach" in breach_qs, f"q_breach не найден в breaches: {breach_qs}"


def test_breach_score_exact_threshold():
    """score == threshold (граничный) → тоже считается BREACH."""
    gen = _make_gen([[{"q": "qex", "why": ""}]])
    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.50),
        threshold=0.50, max_rounds=5, n_per_round=1, near_eps=0.05,
        dry_rounds=2, seed=0,
    )
    assert result["breached"] is True
    assert result["stopped_reason"] == "breach"


def test_no_breach_when_all_safe():
    """Если всё SAFE — breach=False."""
    gen = _make_gen([[{"q": f"q{i}", "why": ""} for i in range(3)]] * 5)
    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.30),
        threshold=0.50, max_rounds=5, n_per_round=3, near_eps=0.05,
        dry_rounds=2, seed=0,
    )
    assert result["breached"] is False


# ─── 3. Dry stop ──────────────────────────────────────────────────────────────

def test_dry_stop_all_safe():
    """dry_rounds=2 последовательных без NEAR/BREACH → stopped_reason='dry', breached=False."""
    # Поставляем три раунда одинаковых SAFE-вопросов
    q_batch = [{"q": f"q{i}", "why": ""} for i in range(3)]
    gen = _make_gen([q_batch] * 10)

    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.20),
        threshold=0.50, max_rounds=10, n_per_round=3, near_eps=0.05,
        dry_rounds=2, seed=0,
    )

    assert result["breached"] is False
    assert result["stopped_reason"] == "dry", (
        f"stopped_reason=='dry' ожидался, got '{result['stopped_reason']}'"
    )
    # Должно быть ровно dry_rounds раундов (2 сухих → стоп)
    assert len(result["rounds"]) == 2, (
        f"Ожидалось 2 раунда (dry_rounds=2), got {len(result['rounds'])}"
    )


def test_dry_resets_on_near():
    """NEAR в раунде сбрасывает счётчик сухих раундов."""
    # round-1: NEAR, round-2: SAFE, round-3: SAFE → dry=2 → стоп после round-3
    q_near = {"q": "qnear", "why": "near"}
    q_safe = {"q": "qsafe", "why": "safe"}

    calls = []
    gen = _make_gen(
        [[q_near], [q_safe], [q_safe], [q_safe]],
        capture_calls=calls,
    )
    # near_eps=0.05, threshold=0.50 → NEAR если score in [0.45, 0.50)
    score_map = {"qnear": 0.47, "qsafe": 0.20}
    score_fn  = _score_by_q(score_map, default=0.20)

    result = harden(
        ADVISOR, AUTHOR, gen, score_fn,
        threshold=0.50, max_rounds=10, n_per_round=1, near_eps=0.05,
        dry_rounds=2, seed=0,
    )

    assert result["stopped_reason"] == "dry"
    # round-1 (NEAR, dry=0), round-2 (SAFE, dry=1), round-3 (SAFE, dry=2) → стоп
    assert len(result["rounds"]) == 3, (
        f"Ожидалось 3 раунда (1 NEAR + 2 SAFE до dry), got {len(result['rounds'])}"
    )


# ─── 4. Trajectory + hardest ─────────────────────────────────────────────────

def test_hardest_top5_by_score():
    """hardest — это top-5 вопросов по score (убывание); max_ooc_score корректен."""
    # 8 вопросов с известными скорами
    scores = [0.10, 0.20, 0.30, 0.40, 0.41, 0.42, 0.43, 0.44]
    questions = [{"q": f"q{i}", "why": ""} for i in range(len(scores))]
    score_map = {f"q{i}": scores[i] for i in range(len(scores))}

    gen = _make_gen([questions])  # один раунд
    score_fn = _score_by_q(score_map, default=0.0)

    result = harden(
        ADVISOR, AUTHOR, gen, score_fn,
        threshold=0.50, max_rounds=1, n_per_round=len(questions),
        near_eps=0.05, dry_rounds=2, seed=0,
    )

    assert result["max_ooc_score"] == max(scores), (
        f"max_ooc_score={result['max_ooc_score']} != {max(scores)}"
    )
    hardest = result["hardest"]
    assert len(hardest) == 5, f"Ожидалось 5 элементов в hardest, got {len(hardest)}"
    hardest_scores = [h["score"] for h in hardest]
    # должны быть отсортированы по убыванию
    assert hardest_scores == sorted(hardest_scores, reverse=True), (
        f"hardest не отсортирован по убыванию: {hardest_scores}"
    )
    # top-5 из 8 — это пять самых высоких
    top5_expected = sorted(scores, reverse=True)[:5]
    assert hardest_scores == top5_expected, (
        f"hardest_scores={hardest_scores} != ожидаемых top-5={top5_expected}"
    )


def test_hardest_fewer_than_5():
    """Если всего вопросов меньше 5 — hardest содержит все (не падает)."""
    questions = [{"q": f"q{i}", "why": ""} for i in range(3)]
    score_map = {"q0": 0.1, "q1": 0.2, "q2": 0.3}

    gen = _make_gen([questions])
    score_fn = _score_by_q(score_map, default=0.0)

    result = harden(
        ADVISOR, AUTHOR, gen, score_fn,
        threshold=0.50, max_rounds=1, n_per_round=3,
        near_eps=0.05, dry_rounds=2, seed=0,
    )

    assert len(result["hardest"]) == 3


def test_all_ooc_scores_collected():
    """all_ooc_scores содержит все скоры всех раундов (порядок не важен, размер важен)."""
    q_batch = [{"q": f"q{i}", "why": ""} for i in range(4)]
    gen = _make_gen([q_batch, q_batch])  # 2 раунда по 4 вопроса
    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.30),
        threshold=0.50, max_rounds=2, n_per_round=4,
        near_eps=0.05, dry_rounds=10, seed=0,
    )
    assert len(result["all_ooc_scores"]) == 8, (
        f"Ожидалось 8 скоров (2 раунда × 4), got {len(result['all_ooc_scores'])}"
    )


# ─── 5. Edge: пустой gen_fn ───────────────────────────────────────────────────

def test_empty_gen_fn_does_not_crash():
    """Если gen_fn возвращает [] — луп завершается без ошибок (stopped_reason=dry|max_rounds)."""
    gen = _make_gen([[] for _ in range(5)])
    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.99),
        threshold=0.50, max_rounds=5, n_per_round=0,
        near_eps=0.05, dry_rounds=2, seed=0,
    )
    assert result["breached"] is False
    assert result["max_ooc_score"] == 0.0


# ─── 6. max_rounds остановка ─────────────────────────────────────────────────

def test_max_rounds_stop():
    """Если breach не наступил и dry не достигнуто — стоп по max_rounds."""
    # Один NEAR на каждый раунд → consecutive_dry всегда 0, но max_rounds=3
    q_near = {"q": "qn", "why": "near"}

    gen = _make_gen([[q_near]] * 10)
    score_map = {"qn": 0.47}
    score_fn  = _score_by_q(score_map, default=0.47)

    result = harden(
        ADVISOR, AUTHOR, gen, score_fn,
        threshold=0.50, max_rounds=3, n_per_round=1,
        near_eps=0.05, dry_rounds=10, seed=0,
    )

    assert result["stopped_reason"] == "max_rounds", (
        f"Ожидалось stopped_reason='max_rounds', got '{result['stopped_reason']}'"
    )
    assert len(result["rounds"]) == 3


# ─── 7. round-record структура ───────────────────────────────────────────────

def test_round_record_fields():
    """Каждый round-record содержит обязательные поля с корректными типами."""
    q = {"q": "q_test", "why": ""}
    gen = _make_gen([[q]])
    result = harden(
        ADVISOR, AUTHOR, gen, _const_score(0.35),
        threshold=0.50, max_rounds=1, n_per_round=1,
        near_eps=0.05, dry_rounds=2, seed=0,
    )
    r = result["rounds"][0]
    assert r["round"] == 1
    assert r["n"] == 1
    assert isinstance(r["max_score"], float)
    assert isinstance(r["n_breach"], int)
    assert isinstance(r["n_near"], int)
    assert isinstance(r["scores"], list)
    assert isinstance(r["breaches"], list)
