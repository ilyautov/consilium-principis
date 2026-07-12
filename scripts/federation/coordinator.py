"""Координатор совета-федерации: разложить план в роль-таски (по N реплик на роль), опросить статус,
собрать кандидатов. Верность сверяет НАШ сервер централизованно (позже)."""
from federation.queue import RoleTask
from federation import judge as _judge


def open_session(backend, session_id, plan, replicas_default=3):
    """plan = [{role, advisor_dir, question, replicas?}]. На каждую роль кладём `replicas` тасков."""
    enqueued = 0
    roles = []
    for item in plan:
        n = int(item.get("replicas", replicas_default))
        for _ in range(n):
            backend.enqueue(RoleTask(session_id, item["role"], item["advisor_dir"],
                                     item["question"]))
        enqueued += n
        roles.append({"role": item["role"], "replicas": n})
    return {"session_id": session_id, "enqueued": enqueued, "roles": roles}


def poll_session(backend, session_id):
    """Счётчики состояний сессии (pending/claimed/done/dead)."""
    return backend.status(session_id)


def _verify_candidate(raw, advisor_dir, verify_fn):
    """Сервер сверяет КАЖДУЮ цитату по ДОВЕРЕННОМУ advisor_dir (из строки таска). Маркеры воркера
    игнорируются — статус ставит только verify_fn (централизованный гейт)."""
    vq = []
    for q in raw.get("quotes", []):
        fc = verify_fn(q.get("text", ""), advisor_dir)
        vq.append({"text": q.get("text", ""), "status": fc.get("status", "🟡"),
                   "source": fc.get("source", "")})
    return {"argument": raw.get("argument", ""), "worker_model": raw.get("worker_model", ""),
            "quotes": vq}


def _assemble_role(role, advisor_dir, rows, verify_fn):
    cands = [_verify_candidate(r["result"], advisor_dir, verify_fn)
             for r in rows if r.get("result")]
    rep = max(cands, key=_judge.score_candidate) if cands else None
    return {"role": role, "advisor_dir": advisor_dir,
            "representative": rep, "replicas": cands,
            "divergence": _judge.divergence(cands),
            "worker_models": [c["worker_model"] for c in cands],
            "verdict": _judge.verdict(rep)}


def assemble(backend, session_id, verify_fn):
    """Собрать совет: сгруппировать по роли, сервер-сверить верность, сохранить дивергенцию и
    идентичность моделей. verify_fn(quote, advisor_dir)->{status,source} инъектируется (наш гейт)."""
    all_rows = backend.results(session_id, status=None)
    done = [r for r in all_rows if r["status"] == "done"]
    # порядок ролей — по первому появлению в сессии; advisor_dir доверенный (из строки таска)
    order, meta = [], {}
    for r in all_rows:
        if r["role"] not in meta:
            meta[r["role"]] = r["advisor_dir"]
            order.append(r["role"])
    roles_out = []
    degraded = []
    for role in order:
        rows = [r for r in done if r["role"] == role]
        if not rows:
            degraded.append(role)
            roles_out.append({"role": role, "advisor_dir": meta[role], "degraded": True,
                              "mode": "host_single_brain", "diversity": "reduced",
                              "verdict": "ESCALATE", "representative": None, "replicas": []})
            continue
        roles_out.append(_assemble_role(role, meta[role], rows, verify_fn))
    return {"session_id": session_id, "roles": roles_out, "degraded_roles": degraded,
            "diversity": "reduced" if degraded else "full"}
