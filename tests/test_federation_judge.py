"""Судья: rule-based рубрика (MVP). score — репрезентант; divergence — сохранение разнообразия;
verdict — PASS/FIX/ESCALATE (именование заимствовано из advisor-orchestrator-worker)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.judge import score_candidate, divergence, verdict


def _cand(arg, statuses):
    return {"argument": arg, "worker_model": "m",
            "quotes": [{"text": "t%d" % i, "status": s, "source": "src"} for i, s in enumerate(statuses)]}


def test_score_rewards_blue_over_green_over_none():
    assert score_candidate(_cand("a", ["🔵"])) > score_candidate(_cand("a", ["🟢"]))
    assert score_candidate(_cand("a", ["🟢"])) > score_candidate(_cand("a", ["🟡"]))
    assert score_candidate(_cand("a", [])) < score_candidate(_cand("a", ["🔵"]))


def test_divergence_low_when_arguments_agree():
    cands = [_cand("ship the mvp fast now", []), _cand("ship the mvp fast now", []),
             _cand("ship the mvp fast", [])]
    d = divergence(cands)
    assert d["level"] == "low" and d["flagged"] is False


def test_divergence_high_when_arguments_diverge():
    cands = [_cand("ship the mvp immediately today", []),
             _cand("wait gather more evidence first", []),
             _cand("abandon the project entirely instead", [])]
    d = divergence(cands)
    assert d["level"] == "high" and d["flagged"] is True and d["score"] >= 0.5


def test_divergence_single_candidate_is_low():
    d = divergence([_cand("solo", [])])
    assert d["level"] == "low" and d["flagged"] is False


def test_verdict_pass_fix_escalate():
    assert verdict(_cand("a", ["🔵"])) == "PASS"          # есть заземление 🔵
    assert verdict(_cand("a", ["🟡"])) == "FIX"           # аргумент есть, грунта нет
    assert verdict(_cand("", [])) == "FIX"                # пустой аргумент, но кандидат есть → FIX
    assert verdict(None) == "ESCALATE"                    # кандидата нет вовсе
