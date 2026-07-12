"""Координатор: open кладёт реплики роль-тасков в очередь; poll читает статус-счётчики."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from federation.queue import SqliteBackend, RoleTask
from federation.coordinator import open_session, poll_session


def _q(tmp_path):
    return SqliteBackend(str(tmp_path / "co.sqlite3"))


def test_open_enqueues_replicas_per_role(tmp_path):
    q = _q(tmp_path)
    plan = [{"role": "aurelius", "advisor_dir": "advisors/aurelius", "question": "Q1", "replicas": 3},
            {"role": "machiavelli", "advisor_dir": "advisors/machiavelli", "question": "Q1"}]
    r = open_session(q, "s1", plan, replicas_default=2)
    assert r["session_id"] == "s1"
    assert r["enqueued"] == 3 + 2                # aurelius×3 + machiavelli×2(дефолт)
    st = q.status("s1")
    assert st["pending"] == 5


def test_poll_returns_status_counts(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "r", "advisor_dir": "advisors/r", "question": "Q"}],
                 replicas_default=2)
    q.claim("w1")
    p = poll_session(q, "s1")
    assert p["pending"] == 1 and p["claimed"] == 1 and p["done"] == 0


from federation.coordinator import assemble
from federation.executor import claim_brief, submit_candidate


def _seed_done(q, session_id, role, advisor_dir, question, argument, quote_texts, model):
    from federation.executor import claim_brief, submit_candidate
    b = claim_brief(q, "w-" + model, roles=[role], timeout=1.0)
    assert b.get("role") == role
    cand = {"argument": argument, "quotes": [{"text": t} for t in quote_texts]}
    submit_candidate(q, b["task_id"], b["worker_id"] if "worker_id" in b else "w-" + model,
                     b["claim_token"], model, cand)


def _fake_verify(quote, advisor_dir):
    # мок централизованного гейта: только точный «REAL» в правильном корпусе → 🔵
    if quote == "REAL" and advisor_dir == "advisors/aurelius":
        return {"status": "🔵", "verbatim": True, "source": "Meditations 7.29"}
    return {"status": "🟡", "verbatim": False, "source": ""}


def test_assemble_server_reverifies_and_downgrades_fake_blue(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 1}])
    # воркер кладёт цитату, которую МОГ БЫ пометить 🔵 — но сервер верит только своему verify
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "Спокойствие.", ["FAKE"], "m1")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert role0["representative"]["quotes"][0]["status"] == "🟡"   # фейк-🔵 понижен сервером


def test_assemble_preserves_divergence_and_model_identity(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 3}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now", ["REAL"], "claude-sonnet-5")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "wait gather evidence first", ["REAL"], "gemini-3")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "abandon project entirely instead", [], "gpt-5")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert len(role0["replicas"]) == 3                          # НЕ схлопнуто в best-of-N
    assert role0["divergence"]["level"] == "high" and role0["divergence"]["flagged"] is True
    assert set(role0["worker_models"]) == {"claude-sonnet-5", "gemini-3", "gpt-5"}  # identity
    # репрезентант выбран рубрикой (у заземлённых 🔵 балл выше пустого)
    assert role0["representative"]["argument"] in ("ship the mvp now", "wait gather evidence first")
    assert role0["verdict"] == "PASS"                           # есть 🔵 → PASS


def test_assemble_agreeing_replicas_low_divergence(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 2}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now", ["REAL"], "m1")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now", ["REAL"], "m2")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    assert out["roles"][0]["divergence"]["level"] == "low"
    assert out["diversity"] == "full"


def test_assemble_partial_completion_not_reported_full(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 3}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship now", ["REAL"], "m1")
    out = assemble(q, "s1", verify_fn=_fake_verify)      # 1 из 3 сыграна
    role0 = out["roles"][0]
    assert role0["replicas_done"] == 1 and role0["replicas_total"] == 3
    assert role0["complete"] is False
    assert out["complete"] is False
    assert out["diversity"] != "full"                    # не «full» пока не все реплики сыграны


def test_assemble_empty_arguments_do_not_fake_consensus(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 4}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "", ["REAL"], "m1")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship the mvp now today fast", ["REAL"], "m2")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "abandon everything immediately legal risk", ["REAL"], "m3")
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "", [], "m4")
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert role0["divergence"]["level"] == "high" and role0["divergence"]["flagged"] is True
    assert len(role0["replicas"]) == 4                   # структурно всё сохранено (анти-best-of-N)


def test_assemble_malformed_row_does_not_crash_whole_session(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [
        {"role": "aurelius", "advisor_dir": "advisors/aurelius", "question": "Q", "replicas": 1},
        {"role": "machiavelli", "advisor_dir": "advisors/machiavelli", "question": "Q", "replicas": 1}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship now", ["REAL"], "m1")
    # напрямую портим machiavelli-строку в обход валидации submit (прямой ack)
    b = claim_brief(q, "wbad", roles=["machiavelli"], timeout=1.0)
    q.ack(b["task_id"], "wbad", b["claim_token"], {"argument": 123, "quotes": "not-a-list"})
    out = assemble(q, "s1", verify_fn=_fake_verify)      # НЕ должен упасть
    by_role = {r["role"]: r for r in out["roles"]}
    assert by_role["aurelius"]["representative"]["argument"] == "ship now"   # здоровая роль цела
    mach = by_role["machiavelli"]
    assert mach.get("errors") or mach["replicas"] == []  # плохая строка изолирована, не уронила сессию


def test_assemble_reports_grounded_replica_count(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 3}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "a", ["REAL"], "m1")   # 🔵
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "b", ["FAKE"], "m2")   # 🟡
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "c", [], "m3")         # нет цитат
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert role0["grounded_replicas"] == 1 and role0["replicas_done"] == 3


def test_open_session_rejects_role_name_collision_diff_advisor(tmp_path):
    import pytest
    q = _q(tmp_path)
    with pytest.raises(ValueError):
        open_session(q, "s1", [
            {"role": "sage", "advisor_dir": "advisors/aurelius", "question": "Q"},
            {"role": "sage", "advisor_dir": "advisors/machiavelli", "question": "Q"}])


def test_assemble_degrades_role_with_no_done_candidates(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [{"role": "aurelius", "advisor_dir": "advisors/aurelius",
                            "question": "Q", "replicas": 2}])
    # ни одного submit → роль пуста
    out = assemble(q, "s1", verify_fn=_fake_verify)
    role0 = out["roles"][0]
    assert role0["degraded"] is True
    assert role0["mode"] == "host_single_brain"
    assert role0["diversity"] == "reduced"
    assert role0["verdict"] == "ESCALATE"
    assert role0["representative"] is None and role0["replicas"] == []
    assert out["diversity"] == "reduced" and "aurelius" in out["degraded_roles"]


def test_assemble_mixed_some_degraded_some_full(tmp_path):
    q = _q(tmp_path)
    open_session(q, "s1", [
        {"role": "aurelius", "advisor_dir": "advisors/aurelius", "question": "Q", "replicas": 1},
        {"role": "machiavelli", "advisor_dir": "advisors/machiavelli", "question": "Q", "replicas": 1}])
    _seed_done(q, "s1", "aurelius", "advisors/aurelius", "Q", "ship now", ["REAL"], "m1")
    # machiavelli не отвечает → деградирует, aurelius полон
    out = assemble(q, "s1", verify_fn=_fake_verify)
    by_role = {r["role"]: r for r in out["roles"]}
    assert by_role["aurelius"].get("degraded") is not True
    assert by_role["machiavelli"]["degraded"] is True
    assert out["diversity"] == "reduced"                      # хоть одна деградировала
    assert out["degraded_roles"] == ["machiavelli"]


def test_assemble_unknown_session_flagged(tmp_path):
    q = _q(tmp_path)
    out = assemble(q, "never-opened", verify_fn=_fake_verify)
    assert out["unknown_session"] is True
    assert out["complete"] is False
    assert out["roles"] == []
