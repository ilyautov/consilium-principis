"""Исполнитель: claim отдаёт СТРУКТУРНЫЙ бриф (не shell-строку — заимствование trust-boundary),
submit валидирует и кладёт сырьё через ack (маркеры НЕ ставит — сервер сверит на assemble)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.queue import SqliteBackend, RoleTask
from federation.executor import claim_brief, heartbeat_task


def _q(tmp_path):
    return SqliteBackend(str(tmp_path / "ex.sqlite3"))


def test_claim_brief_returns_structural_brief(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "aurelius", "advisors/aurelius", "Как быть?"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    assert b["role"] == "aurelius"
    assert b["advisor_dir"] == "advisors/aurelius"
    assert b["question"] == "Как быть?"
    assert isinstance(b["task_id"], str) and isinstance(b["claim_token"], str)
    # бриф — данные, НЕ собранная команда: никаких shell-строк
    assert "$(" not in repr(b) and "`" not in repr(b)


def test_claim_brief_empty_when_none(tmp_path):
    q = _q(tmp_path)
    b = claim_brief(q, "w1", roles=None, timeout=0.2)
    assert b == {"empty": True}


def test_heartbeat_roundtrip(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    hb = heartbeat_task(q, b["task_id"], "w1", b["claim_token"])
    assert hb.get("ok") is True
    stale = heartbeat_task(q, b["task_id"], "w1", "wrong-token")
    assert stale.get("stale") is True


from federation.executor import submit_candidate


def test_submit_valid_candidate_stored_raw(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    cand = {"argument": "Сохраняй спокойствие.", "quotes": [{"text": "Confine thyself"}]}
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "claude-sonnet-5", cand)
    assert r.get("ok") is True
    rows = q.results("s1")
    stored = rows[0]["result"]
    assert stored["argument"] == "Сохраняй спокойствие."
    assert stored["quotes"] == [{"text": "Confine thyself"}]   # только text — без маркеров
    assert stored["worker_model"] == "claude-sonnet-5"         # model identity сохранена


def test_submit_stale_claim_token_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", "wrong-token", "m",
                         {"argument": "x", "quotes": []})
    assert r.get("rejected")
    assert q.results("s1") == []                               # ничего не записано (не done)


def test_submit_oversize_argument_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": "x" * 9000, "quotes": []})
    assert r.get("rejected") and "argument" in r["rejected"]


def test_submit_non_string_argument_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": {"nope": 1}, "quotes": []})
    assert r.get("rejected")


def test_submit_control_chars_sanitized(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": "clean\x07here\ttab", "quotes": [{"text": "ok\x00bye"}]})
    assert r.get("ok") is True
    stored = q.results("s1")[0]["result"]
    assert "\x07" not in stored["argument"] and "\t" in stored["argument"]  # \x07 срезан, \t цел
    assert "\x00" not in stored["quotes"][0]["text"]


def test_submit_too_many_quotes_rejected(tmp_path):
    q = _q(tmp_path)
    q.enqueue(RoleTask("s1", "r", "advisors/r", "Q"))
    b = claim_brief(q, "w1", roles=None, timeout=1.0)
    r = submit_candidate(q, b["task_id"], "w1", b["claim_token"], "m",
                         {"argument": "x", "quotes": [{"text": "t"}] * 40})
    assert r.get("rejected") and "quotes" in r["rejected"]
