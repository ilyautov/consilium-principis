"""§1.2 moat-v2: early-exit судейство в cite (двухпроходное, review HIGH-1).

Было: cite судит ВЕСЬ пул кандидатов (~38 вызовов судьи), потом режет top-limit —
минуты латентности. Стало: пасс 1 — дешёвый verbatim-тиринг всего пула в порядке
убывания primary-косинуса (без primary-скора — последними) → партиции 🔵/🟢; пасс 2 —
судья ЛЕНИВО: сперва 🔵 до набора limit, 🟢 судятся ТОЛЬКО на остаток. Инвариант
контракта: 🔵 (первоисточник) приоритетен для ВКЛЮЧЕНИЯ, не только подачи — 🟢 с более
высоким косинусом НЕ вытесняет прошедший 🔵. Вызовов судьи ≈ limit + K (реджекты);
fail-closed сохранён (гейт бросил → кандидат снят, скан продолжается).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pytest
import mcp_server
import relevance_gate
from engine import retrieval


def _pool(n, start=0.95, step=0.02):
    """n кандидатов с убывающим primary-скором: passage-00 самый близкий."""
    return [{"text": f"passage-{i:02d} body of the candidate", "score": round(start - i * step, 4),
             "source": "corpus.jsonl"} for i in range(n)]


@pytest.fixture()
def cite_env(monkeypatch):
    """Мокнутый пул из 20 кандидатов + все verbatim-🔵 + судья-счётчик через gate_quote."""
    pool = _pool(20)
    monkeypatch.setattr(retrieval, "retrieve", lambda q, adv, top_k=8: list(pool))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda quote, adv: {"status": "🔵", "verbatim": True, "source": "src"})
    calls = []

    def make_gate(reject=(), boom=()):
        def gate(query, text, score, advisor_dir, cfg=None, source=None, raw_score=None):
            calls.append(text)
            if any(r in text for r in boom):
                raise RuntimeError("судья упал")
            return not any(r in text for r in reject)
        return gate
    return pool, calls, make_gate


def _texts(r):
    return [q["text"] for q in r["quotes"]]


def test_early_exit_stops_at_limit(cite_env, monkeypatch):
    # все кандидаты проходят → судим РОВНО limit из 20 (не весь пул)
    pool, calls, make_gate = cite_env
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate())
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=4)
    assert len(calls) == 4                            # ≤ limit + K, K=0 → ровно limit
    assert _texts(r) == [p["text"] for p in pool[:4]]  # top-4 по убыванию косинуса


def test_judge_calls_bounded_by_limit_plus_rejections(cite_env, monkeypatch):
    # судья режет 3 кандидатов из головы → вызовов limit+K, сильно меньше пула
    pool, calls, make_gate = cite_env
    reject = ("passage-01", "passage-03", "passage-05")
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate(reject=reject))
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=4)
    assert len(calls) == 4 + len(reject)              # limit + K
    assert len(calls) < len(pool)                     # ощутимо меньше полного скана
    assert _texts(r) == ["passage-00 body of the candidate", "passage-02 body of the candidate",
                         "passage-04 body of the candidate", "passage-06 body of the candidate"]


def test_result_identical_to_full_scan_on_uniform_tier(cite_env, monkeypatch):
    # эталон НА ОДНОТИРНОМ пуле (все 🔵): полный прогон (судим всех, топ-limit прошедших
    # по косинусу) == early-exit. На СМЕШАННОМ пуле равенства глобальному top-limit НЕТ
    # намеренно: 🔵 приоритетен для включения (см. test_blue_included_ahead_of_greens).
    pool, calls, make_gate = cite_env
    reject = ("passage-02", "passage-07")
    gate = make_gate(reject=reject)
    full = [p["text"] for p in pool if not any(x in p["text"] for x in reject)][:4]
    monkeypatch.setattr(relevance_gate, "gate_quote", gate)
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=4)
    assert _texts(r) == full


def test_fail_closed_gate_raise_skips_and_continues(cite_env, monkeypatch):
    # гейт бросил на кандидате → кандидат снят (НЕ 🔵 «на всякий»), скан продолжается
    pool, calls, make_gate = cite_env
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate(boom=("passage-00",)))
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=4)
    assert "passage-00 body of the candidate" not in _texts(r)
    assert _texts(r) == [p["text"] for p in pool[1:5]]  # следующие 4 добраны


def test_candidates_without_primary_score_sort_last(cite_env, monkeypatch):
    # кандидат вторичного запроса (primary его не находил) судится ПОСЛЕДНИМ, но судится
    pool, calls, make_gate = cite_env
    primary = _pool(3)
    kernel_only = [{"text": "kernel-only candidate text", "score": 0.99, "source": "corpus.jsonl"}]

    def retrieve(q, adv, top_k=8):
        return list(primary) if q == "q" else list(kernel_only)
    monkeypatch.setattr(retrieval, "retrieve", retrieve)
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate())
    monkeypatch.setattr(mcp_server, "_kernel_themes", lambda adv, limit=6: ["kernel theme"])
    r = mcp_server._cite("advisors/x", "q", use_kernels=True, limit=4)
    # несмотря на score=0.99 у kernel-кандидата, он БЕЗ primary-скора → в хвосте
    assert _texts(r) == [p["text"] for p in primary] + ["kernel-only candidate text"]
    assert calls[-1] == "kernel-only candidate text"


def test_non_verbatim_candidates_never_reach_judge(cite_env, monkeypatch):
    # не-verbatim кандидат отсеян ДО судьи (дешёвый гейт первым) и не ест лимит вызовов
    pool, calls, make_gate = cite_env

    def fidelity(quote, adv):
        if "passage-00" in quote or "passage-01" in quote:
            return {"status": "🟡", "verbatim": False, "source": ""}
        return {"status": "🔵", "verbatim": True, "source": "src"}
    monkeypatch.setattr(mcp_server, "_fidelity_check", fidelity)
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate())
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=4)
    assert len(calls) == 4 and not any("passage-00" in c or "passage-01" in c for c in calls)
    assert _texts(r) == [p["text"] for p in pool[2:6]]


def _fidelity_by_blue_set(blue_substrings):
    """_fidelity_check-мок: 🔵 только для перечисленных кандидатов, остальные — 🟢 (verbatim)."""
    def fidelity(quote, adv):
        blue = any(b in quote for b in blue_substrings)
        return {"status": "🔵" if blue else "🟢", "verbatim": True, "source": "src"}
    return fidelity


def test_blue_included_ahead_of_greens(cite_env, monkeypatch):
    # HIGH-1 review: 🔵 приоритетен для ВКЛЮЧЕНИЯ — низкокосинусный прошедший 🔵 НЕ
    # вытесняется 🟢 с более высоким косинусом (контрпример master-контракта: limit=2,
    # 🟢0.95, 🟢0.93, ... 🔵 глубоко в хвосте → {🔵, топ-🟢}, а не {🟢, 🟢})
    pool, calls, make_gate = cite_env
    monkeypatch.setattr(mcp_server, "_fidelity_check", _fidelity_by_blue_set(("passage-15",)))
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate())
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=2)
    assert _texts(r) == ["passage-15 body of the candidate",   # 🔵 включён, хотя косинус ниже
                         "passage-00 body of the candidate"]   # 🟢 доливает остаток (топ по косинусу)
    assert [q["marker"] for q in r["quotes"]] == ["🔵", "🟢"]
    assert r["best"]["marker"] == "🔵"
    assert len(calls) == 2                            # early-exit жив: limit вызовов, не пул


def test_greens_fill_only_remainder_after_blues(cite_env, monkeypatch):
    # 🟢 судятся ТОЛЬКО когда прошедших 🔵 не хватило на limit; внутри тира — по косинусу
    pool, calls, make_gate = cite_env
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        _fidelity_by_blue_set(("passage-07", "passage-09")))
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate())
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=3)
    assert _texts(r) == ["passage-07 body of the candidate",   # оба 🔵 (в порядке косинуса)
                         "passage-09 body of the candidate",
                         "passage-00 body of the candidate"]   # + один 🟢 на остаток
    assert [q["marker"] for q in r["quotes"]] == ["🔵", "🔵", "🟢"]
    assert len(calls) == 3                            # каждый судился один раз, ровно limit


def test_enough_blues_means_no_green_judged(cite_env, monkeypatch):
    # прошедших 🔵 хватает на limit → 🟢 вообще не доходят до судьи
    pool, calls, make_gate = cite_env
    blues = ("passage-03", "passage-08", "passage-12")
    monkeypatch.setattr(mcp_server, "_fidelity_check", _fidelity_by_blue_set(blues))
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate())
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=3)
    assert [q["marker"] for q in r["quotes"]] == ["🔵", "🔵", "🔵"]
    assert all(any(b in c for b in blues) for c in calls)      # судились только 🔵
    assert len(calls) == 3


def test_call_count_bounded_on_mixed_tiers_with_rejections(cite_env, monkeypatch):
    # смешанный пул + реджект 🔵: вызовов limit+K, сильно меньше пула; 🟢 доливают остаток
    pool, calls, make_gate = cite_env
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        _fidelity_by_blue_set(("passage-06", "passage-11")))
    monkeypatch.setattr(relevance_gate, "gate_quote", make_gate(reject=("passage-11",)))
    r = mcp_server._cite("advisors/x", "q", use_kernels=False, limit=3)
    assert _texts(r) == ["passage-06 body of the candidate",   # 🔵 прошёл (11 срезан судьёй)
                         "passage-00 body of the candidate",   # 🟢 остаток по косинусу
                         "passage-01 body of the candidate"]
    assert len(calls) == 3 + 1                        # limit + K (один реджект)
    assert len(calls) < len(pool)
