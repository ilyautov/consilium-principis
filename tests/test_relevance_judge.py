"""LLM-as-judge eval — все тесты offline (мок llm, фейковый ретривер, сеть не трогается)."""
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import llm_local
import relevance_judge


# ── judge: парсинг ответа ────────────────────────────────────────────────────

def test_judge_parses_bare_digit_3(monkeypatch):
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "3")
    assert relevance_judge.judge("вопрос", "пассаж") == 3


def test_judge_parses_rating_format(monkeypatch):
    """'Rating: 2' → ровно одна цифра 0-3 в строке → однозначно → 2."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "Rating: 2")
    assert relevance_judge.judge("вопрос", "пассаж") == 2


def test_judge_parses_digit_1(monkeypatch):
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "Оценка: 1 (касается темы)")
    assert relevance_judge.judge("вопрос", "пассаж") == 1


def test_judge_parses_digit_0(monkeypatch):
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "0")
    assert relevance_judge.judge("вопрос", "пассаж") == 0


# ── judge: FAIL-CLOSED (непарсируемое = нерелевантное, никогда не завышать) ─

def test_judge_fail_closed_no_digit(monkeypatch):
    """Ответ без валидной цифры 0-3 → 0 (fail-closed, не завышать)."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "I cannot rate this")
    assert relevance_judge.judge("вопрос", "пассаж") == 0


def test_judge_fail_closed_empty_response(monkeypatch):
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "")
    assert relevance_judge.judge("вопрос", "пассаж") == 0


def test_judge_fail_closed_only_high_digits(monkeypatch):
    """Только цифры 4-9 в ответе (без 0-3) → 0 (fail-closed)."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "rating: 4/5, very high")
    assert relevance_judge.judge("вопрос", "пассаж") == 0


def test_judge_no_inflation_from_prose_two_digits(monkeypatch):
    """MOAT-SAFE: проза с ДВУМЯ цифрами 0-3 ("not a 3, it's a 0") неоднозначна →
    0 (fail-closed), а не 3. Инвариант: никогда не завышать балл."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "not a 3, it's a 0")
    assert relevance_judge.judge("вопрос", "пассаж") == 0


def test_judge_no_inflation_high_first_low_second(monkeypatch):
    """Даже когда первая цифра высокая: "the score is not 3 but 1" — две цифры 0-3
    → неоднозначно → 0. Наивный re.search взял бы 3 (завышение) — здесь исключено."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "the score is not 3 but 1")
    assert relevance_judge.judge("вопрос", "пассаж") == 0


# ── _ndcg: unit-тесты формулы (рассчитываемые вручную) ──────────────────────

def test_ndcg_known_rels_3_0_1():
    """rels=[3,0,1] — рукопроверяемый кейс.

    DCG  = 3/log2(2) + 0/log2(3) + 1/log2(4) = 3/1 + 0 + 0.5 = 3.5
    IDCG = 3/log2(2) + 1/log2(3) + 0/log2(4) = 3 + 1/log2(3)
    nDCG = 3.5 / (3 + 1/log2(3))
    """
    rels = [3, 0, 1]
    dcg = 3 / math.log2(2) + 0 / math.log2(3) + 1 / math.log2(4)
    idcg = 3 / math.log2(2) + 1 / math.log2(3) + 0 / math.log2(4)
    expected = dcg / idcg
    assert relevance_judge._ndcg(rels) == pytest.approx(expected, rel=1e-9)


def test_ndcg_all_zeros():
    """Все нули → IDCG=0 → nDCG=0 (без деления на ноль)."""
    assert relevance_judge._ndcg([0, 0, 0]) == 0.0


def test_ndcg_perfect_ordering():
    """Убывающий порядок = IDCG → nDCG = 1.0."""
    assert relevance_judge._ndcg([3, 2, 1]) == pytest.approx(1.0, rel=1e-9)


def test_ndcg_worst_ordering():
    """Возрастающий порядок → nDCG < 1 (не идеал)."""
    assert relevance_judge._ndcg([1, 2, 3]) < 1.0


# ── retrieval_eval_judged: интеграционные тесты через test seam ──────────────

def _fake_retrieve(passages_by_call):
    """Возвращает retrieve_fn, отдающую passages_by_call[i] на i-й вызов (по кругу)."""
    state = {"n": 0}

    def _fn(query, advisor_dir, top_k):
        idx = state["n"] % len(passages_by_call)
        state["n"] += 1
        return [{"text": p, "score": 0.9, "source": "fake"} for p in passages_by_call[idx][:top_k]]

    return _fn


def test_retrieval_eval_judged_single_query_known_rels(monkeypatch):
    """Один вопрос, rels=[3,0,1] (threshold=2).

    Ожидаем:
      hit@3       = 1.0        (rel=3 >= 2 → есть попадание)
      precision@3 = 1/3 ≈ 0.333 (1 пассаж из 3 rel>=2)
      nDCG@3      = 3.5 / (3 + 1/log2(3))  (рукопроверяемо)
    """
    passages = ["passage_high", "passage_low", "passage_mid"]
    score_map = {"passage_high": 3, "passage_low": 0, "passage_mid": 1}

    def fake_generate(prompt, model=None, temperature=0.3, timeout=120):
        for text, score in score_map.items():
            if text in prompt:
                return str(score)
        return "0"

    monkeypatch.setattr(llm_local, "generate", fake_generate)

    golden = [{"q": "тестовый вопрос", "anchor": "якорь", "ref": "Test I"}]
    result = relevance_judge.retrieval_eval_judged(
        advisor_dir="/fake/advisor",
        golden=golden,
        top_k=3,
        rel_threshold=2,
        retrieve_fn=_fake_retrieve([passages]),
    )

    assert result["n"] == 1
    assert result["hit_at_k"] == pytest.approx(1.0)
    assert result["precision_at_k"] == pytest.approx(1 / 3, rel=1e-3)

    dcg = 3 / math.log2(2) + 0 / math.log2(3) + 1 / math.log2(4)
    idcg = 3 / math.log2(2) + 1 / math.log2(3) + 0 / math.log2(4)
    assert result["ndcg_at_k"] == pytest.approx(dcg / idcg, rel=1e-3)

    pq = result["per_query"][0]
    assert pq["rels"] == [3, 0, 1]
    assert pq["hit_at_k"] == 1
    assert pq["ref"] == "Test I"


def test_retrieval_eval_judged_no_hit(monkeypatch):
    """Все пассажи ниже порога (rel=1 < threshold=2) → hit@k=0, precision@k=0."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "1")

    golden = [{"q": "вопрос", "anchor": "якорь", "ref": "ref"}]
    result = relevance_judge.retrieval_eval_judged(
        advisor_dir="/fake",
        golden=golden,
        top_k=3,
        rel_threshold=2,
        retrieve_fn=_fake_retrieve([["p1", "p2", "p3"]]),
    )

    assert result["hit_at_k"] == 0.0
    assert result["precision_at_k"] == 0.0


def test_retrieval_eval_judged_two_queries_means(monkeypatch):
    """Два вопроса — проверяем корректное усреднение метрик.

    q1: rels=[3,0,1] → hit=1, prec=1/3
    q2: rels=[0,2,0] → hit=1, prec=1/3
    mean hit = 1.0, mean prec = 1/3
    """
    call_seq = [3, 0, 1, 0, 2, 0]  # по одному per judge-вызов
    state = {"i": 0}

    def fake_generate(prompt, model=None, temperature=0.3, timeout=120):
        val = call_seq[state["i"] % len(call_seq)]
        state["i"] += 1
        return str(val)

    monkeypatch.setattr(llm_local, "generate", fake_generate)

    golden = [
        {"q": "вопрос 1", "anchor": "a1", "ref": "r1"},
        {"q": "вопрос 2", "anchor": "a2", "ref": "r2"},
    ]
    result = relevance_judge.retrieval_eval_judged(
        advisor_dir="/fake",
        golden=golden,
        top_k=3,
        rel_threshold=2,
        retrieve_fn=_fake_retrieve([["p1", "p2", "p3"], ["p4", "p5", "p6"]]),
    )

    assert result["n"] == 2
    assert result["hit_at_k"] == pytest.approx(1.0, rel=1e-3)
    assert result["precision_at_k"] == pytest.approx(1 / 3, rel=1e-3)

    # q1: rels=[3,0,1], q2: rels=[0,2,0]
    assert result["per_query"][0]["rels"] == [3, 0, 1]
    assert result["per_query"][1]["rels"] == [0, 2, 0]


def test_retrieval_eval_judged_empty_golden(monkeypatch):
    """Пустой golden → n=0, все метрики 0."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "3")
    result = relevance_judge.retrieval_eval_judged(
        advisor_dir="/fake",
        golden=[],
        top_k=3,
        retrieve_fn=_fake_retrieve([[]]),
    )
    assert result["n"] == 0
    assert result["hit_at_k"] == 0.0
    assert result["ndcg_at_k"] == 0.0


def test_retrieval_eval_judged_fewer_passages_than_topk(monkeypatch):
    """Если движок вернул < top_k пассажей — дополняем нулями, метрики не падают."""
    monkeypatch.setattr(llm_local, "generate", lambda *a, **kw: "3")

    golden = [{"q": "вопрос", "anchor": "a", "ref": "r"}]
    # retrieve_fn вернёт только 1 пассаж при top_k=3
    result = relevance_judge.retrieval_eval_judged(
        advisor_dir="/fake",
        golden=golden,
        top_k=3,
        rel_threshold=2,
        retrieve_fn=_fake_retrieve([["only_one_passage"]]),
    )

    assert result["n"] == 1
    pq = result["per_query"][0]
    # 1 реальный (rel=3) + 2 паддинг (rel=0)
    assert pq["rels"] == [3, 0, 0]
    assert pq["hit_at_k"] == 1
