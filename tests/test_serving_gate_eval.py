"""tests/test_serving_gate_eval.py — офлайн-тесты серверной поверхности MCP.

Нет ollama, нет реального корпуса, нет сети.
cite_fn / retrieve_fn / judge_fn подаются как test seams.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import serving_gate_eval as sge

FAKE_ADVISOR = "advisors/test-advisor"


# ─────────────────────────── cite_misapplication_rate ───────────────────────────

class TestCiteMisapplicationRate:

    def _ooc(self, n=5):
        return [{"q": f"OOC question {i}", "why": "unanswerable"} for i in range(n)]

    def test_rate_zero_when_cite_returns_empty(self):
        """cite_fn always returns no quotes → rate=0.0"""
        def fake_cite(advisor_dir, query):
            return {"quotes": [], "best": None, "note": "нет дословного"}

        result = sge.cite_misapplication_rate(FAKE_ADVISOR, self._ooc(5), cite_fn=fake_cite)
        assert result["rate"] == 0.0
        assert result["n"] == 5
        assert all(r["n_grounded"] == 0 for r in result["per_q"])

    def test_rate_one_when_all_ooc_get_grounded_blue(self):
        """cite_fn always returns 🔵 quote → rate=1.0"""
        def fake_cite(advisor_dir, query):
            return {
                "quotes": [{"text": "verbatim quote", "source": "src", "marker": "🔵"}],
                "best": {"quote": {"text": "verbatim quote", "source": "src"}, "marker": "🔵"},
                "note": "ok",
            }

        result = sge.cite_misapplication_rate(FAKE_ADVISOR, self._ooc(4), cite_fn=fake_cite)
        assert result["rate"] == 1.0
        assert result["n"] == 4

    def test_rate_one_when_all_ooc_get_grounded_green(self):
        """cite_fn always returns 🟢 quote → still counted as grounded → rate=1.0"""
        def fake_cite(advisor_dir, query):
            return {
                "quotes": [{"text": "secondary quote", "source": "src", "marker": "🟢"}],
                "best": None,
                "note": "",
            }

        result = sge.cite_misapplication_rate(FAKE_ADVISOR, self._ooc(3), cite_fn=fake_cite)
        assert result["rate"] == 1.0

    def test_rate_partial(self):
        """cite_fn returns grounded quote for even-indexed questions only → rate=0.5"""
        def fake_cite(advisor_dir, query):
            idx = int(query.split()[-1])
            if idx % 2 == 0:
                return {"quotes": [{"text": "v", "source": "s", "marker": "🟢"}],
                        "best": None, "note": ""}
            return {"quotes": [], "best": None, "note": "нет"}

        ooc = [{"q": f"OOC question {i}", "why": "x"} for i in range(4)]
        result = sge.cite_misapplication_rate(FAKE_ADVISOR, ooc, cite_fn=fake_cite)
        assert result["rate"] == 0.5
        assert result["n"] == 4

    def test_per_q_detail_tracks_markers(self):
        """per_q tracks n_grounded and markers correctly for multiple quotes"""
        def fake_cite(advisor_dir, query):
            return {
                "quotes": [
                    {"text": "a", "source": "s", "marker": "🔵"},
                    {"text": "b", "source": "s", "marker": "🟢"},
                ],
                "best": None,
                "note": "",
            }

        result = sge.cite_misapplication_rate(FAKE_ADVISOR, [{"q": "q", "why": "w"}],
                                              cite_fn=fake_cite)
        row = result["per_q"][0]
        assert row["n_grounded"] == 2
        assert set(row["markers"]) == {"🔵", "🟢"}

    def test_yellow_marker_not_counted_as_grounded(self):
        """🟡 marker is NOT grounded — should not be counted"""
        def fake_cite(advisor_dir, query):
            return {
                "quotes": [{"text": "t", "source": "s", "marker": "🟡"}],
                "best": None,
                "note": "",
            }

        result = sge.cite_misapplication_rate(FAKE_ADVISOR, [{"q": "q", "why": "w"}],
                                              cite_fn=fake_cite)
        assert result["rate"] == 0.0
        assert result["per_q"][0]["n_grounded"] == 0

    def test_empty_ooc_list(self):
        result = sge.cite_misapplication_rate(FAKE_ADVISOR, [],
                                              cite_fn=lambda d, q: {"quotes": []})
        assert result["rate"] == 0.0
        assert result["n"] == 0
        assert result["per_q"] == []


# ─────────────────────────── judge_gate_efficacy ─────────────────────────────

class TestJudgeGateEfficacy:

    def _make_retrieve_fn(self, score_map):
        """retrieve_fn returning single passage with score from score_map."""
        def retrieve_fn(q, advisor_dir, top_k):
            score = score_map.get(q, 0.0)
            return [{"text": f"passage for {q}", "score": score, "source": "corpus"}]
        return retrieve_fn

    def _make_judge_fn(self, score_map):
        """judge_fn returning score from score_map by query."""
        def judge_fn(q, passage):
            return score_map.get(q, 0)
        return judge_fn

    def test_perfect_separation_tnr_1_tpr_1(self):
        """OOC passages judge <2, answerable >=2 → TNR=1.0, TPR=1.0, false_accept=0.0"""
        ooc_qs = [{"q": "ooc1"}, {"q": "ooc2"}]
        ans_qs = [{"q": "ans1"}, {"q": "ans2"}]

        judge_fn   = self._make_judge_fn({"ooc1": 0, "ooc2": 1, "ans1": 2, "ans2": 3})
        retrieve_fn = self._make_retrieve_fn({"ooc1": 0.3, "ooc2": 0.4, "ans1": 0.8, "ans2": 0.9})

        result = sge.judge_gate_efficacy(
            FAKE_ADVISOR, ooc_qs, ans_qs,
            retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=1, rel_threshold=2,
        )
        assert result["ooc_true_negative_rate"] == 1.0
        assert result["ans_true_positive_rate"] == 1.0
        assert result["ooc_false_accept"] == 0.0
        assert result["n_ooc"] == 2
        assert result["n_ans"] == 2

    def test_leaky_gate_one_ooc_escapes(self):
        """One OOC question judges >=2 → false_accept = 1/3"""
        ooc_qs = [{"q": "ooc1"}, {"q": "ooc2"}, {"q": "ooc3"}]
        ans_qs = [{"q": "ans1"}]

        # ooc2 gets judge=3 → leaks through
        judge_fn    = self._make_judge_fn({"ooc1": 1, "ooc2": 3, "ooc3": 0, "ans1": 2})
        retrieve_fn = self._make_retrieve_fn({q["q"]: 0.6 for q in ooc_qs + ans_qs})

        result = sge.judge_gate_efficacy(
            FAKE_ADVISOR, ooc_qs, ans_qs,
            retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=1, rel_threshold=2,
        )
        assert abs(result["ooc_false_accept"] - 1/3) < 0.001
        assert abs(result["ooc_true_negative_rate"] - 2/3) < 0.001
        assert result["ans_true_positive_rate"] == 1.0

    def test_per_q_decision_and_max_judge(self):
        """Per-question decision and max_judge are correctly tracked."""
        ooc_qs = [{"q": "ooc1"}]
        ans_qs = [{"q": "ans1"}]
        judge_fn    = self._make_judge_fn({"ooc1": 1, "ans1": 3})
        retrieve_fn = self._make_retrieve_fn({"ooc1": 0.3, "ans1": 0.9})

        result = sge.judge_gate_efficacy(
            FAKE_ADVISOR, ooc_qs, ans_qs,
            retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=1, rel_threshold=2,
        )
        assert result["ooc_per_q"][0]["decision"] == "GATE"
        assert result["ooc_per_q"][0]["max_judge"] == 1
        assert result["ans_per_q"][0]["decision"] == "PASS"
        assert result["ans_per_q"][0]["max_judge"] == 3

    def test_empty_passages_gates_question(self):
        """retrieve_fn returning [] → max_judge=0 → GATE (fail-closed)."""
        ooc_qs = [{"q": "ooc1"}]
        result = sge.judge_gate_efficacy(
            FAKE_ADVISOR, ooc_qs, [],
            retrieve_fn=lambda q, d, k: [],
            judge_fn=lambda q, p: 3,  # would pass if called — but no passages
            top_k=3, rel_threshold=2,
        )
        assert result["ooc_true_negative_rate"] == 1.0
        assert result["ooc_false_accept"] == 0.0

    def test_threshold_boundary_exactly_at_threshold(self):
        """max_judge == rel_threshold exactly → PASS (>= not >)."""
        ans_qs = [{"q": "ans1"}]
        judge_fn    = self._make_judge_fn({"ans1": 2})  # exactly at threshold=2
        retrieve_fn = self._make_retrieve_fn({"ans1": 0.8})

        result = sge.judge_gate_efficacy(
            FAKE_ADVISOR, [], ans_qs,
            retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=1, rel_threshold=2,
        )
        assert result["ans_true_positive_rate"] == 1.0

    def test_empty_both_lists(self):
        result = sge.judge_gate_efficacy(
            FAKE_ADVISOR, [], [],
            retrieve_fn=lambda q, d, k: [],
            judge_fn=lambda q, p: 0,
        )
        assert result["ooc_true_negative_rate"] == 0.0
        assert result["ans_true_positive_rate"] == 0.0
        assert result["ooc_false_accept"] == 0.0
        assert result["n_ooc"] == 0
        assert result["n_ans"] == 0


# ─────────────────────────── cosine_false_accept_rate ────────────────────────

class TestCosineVsJudgeComparison:

    def test_judge_better_than_cosine(self):
        """Cosine passes all OOC (score≥0.5), judge gates all (max_judge<2) → judge wins."""
        ooc_qs = [{"q": "ooc1"}, {"q": "ooc2"}, {"q": "ooc3"}]

        def retrieve_fn(q, d, k):
            return [{"text": f"p {q}", "score": 0.7, "source": "corpus"}]

        def judge_fn(q, p):
            return 1  # always below threshold 2

        cosine_res = sge.cosine_false_accept_rate(
            FAKE_ADVISOR, ooc_qs, retrieve_fn=retrieve_fn, top_k=1)
        judge_res  = sge.judge_gate_efficacy(
            FAKE_ADVISOR, ooc_qs, [],
            retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=1, rel_threshold=2)

        assert cosine_res["false_accept_rate"] == 1.0
        assert judge_res["ooc_false_accept"] == 0.0
        assert judge_res["ooc_false_accept"] < cosine_res["false_accept_rate"]

    def test_cosine_zero_when_all_below_threshold(self):
        """All scores below 0.50 → cosine false_accept=0.0"""
        ooc_qs = [{"q": "q1"}, {"q": "q2"}]

        def retrieve_fn(q, d, k):
            return [{"text": "p", "score": 0.3, "source": "corpus"}]

        result = sge.cosine_false_accept_rate(FAKE_ADVISOR, ooc_qs, retrieve_fn=retrieve_fn)
        assert result["false_accept_rate"] == 0.0
        assert result["n"] == 2

    def test_cosine_exactly_at_threshold_passes(self):
        """Score exactly at 0.50 → PASS (>= not >)."""
        ooc_qs = [{"q": "q1"}]

        def retrieve_fn(q, d, k):
            return [{"text": "p", "score": 0.50, "source": "corpus"}]

        result = sge.cosine_false_accept_rate(
            FAKE_ADVISOR, ooc_qs, retrieve_fn=retrieve_fn, cosine_threshold=0.50)
        assert result["false_accept_rate"] == 1.0

    def test_cosine_empty_passages_no_accept(self):
        """Empty passages list → max_score=0 → GATE."""
        ooc_qs = [{"q": "q1"}]
        result = sge.cosine_false_accept_rate(
            FAKE_ADVISOR, ooc_qs, retrieve_fn=lambda q, d, k: [], top_k=1)
        assert result["false_accept_rate"] == 0.0

    def test_per_q_records_max_score(self):
        ooc_qs = [{"q": "q1"}]

        def retrieve_fn(q, d, k):
            return [{"text": "p", "score": 0.77, "source": "corpus"}]

        result = sge.cosine_false_accept_rate(FAKE_ADVISOR, ooc_qs, retrieve_fn=retrieve_fn)
        assert result["per_q"][0]["max_score"] == 0.77
        assert result["per_q"][0]["decision"] == "PASS"

    def test_judge_gate_with_partial_cosine_leak(self):
        """Mixed: 2 of 3 OOC have high cosine (leak), but judge gates all 3 → rescue=2/3."""
        ooc_qs = [{"q": "ooc1"}, {"q": "ooc2"}, {"q": "ooc3"}]

        score_map = {"ooc1": 0.7, "ooc2": 0.6, "ooc3": 0.3}  # cosine: 2 leak
        judge_map = {"ooc1": 1,   "ooc2": 0,   "ooc3": 1}    # judge: all gated

        def retrieve_fn(q, d, k):
            return [{"text": f"p {q}", "score": score_map.get(q, 0.0), "source": "c"}]

        def judge_fn(q, p):
            return judge_map.get(q, 0)

        cosine_res = sge.cosine_false_accept_rate(
            FAKE_ADVISOR, ooc_qs, retrieve_fn=retrieve_fn, top_k=1)
        judge_res  = sge.judge_gate_efficacy(
            FAKE_ADVISOR, ooc_qs, [],
            retrieve_fn=retrieve_fn, judge_fn=judge_fn,
            top_k=1, rel_threshold=2)

        assert abs(cosine_res["false_accept_rate"] - 2/3) < 0.001
        assert judge_res["ooc_false_accept"] == 0.0
