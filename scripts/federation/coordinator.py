"""Координатор совета-федерации: разложить план в роль-таски (по N реплик на роль), опросить статус,
собрать кандидатов. Верность сверяет НАШ сервер централизованно (позже)."""
from federation.queue import RoleTask
from federation import judge as _judge


def open_session(backend, session_id, plan, replicas_default=3):
    """plan = [{role, advisor_dir, question, replicas?}]. На каждую роль кладём `replicas` тасков.
    Fail-closed: одна и та же роль с РАЗНЫМ advisor_dir → ValueError (иначе assemble сверил бы обе
    против первого корпуса — межкорпусная мис-атрибуция)."""
    seen = {}
    for item in plan:
        role, adir = item["role"], item["advisor_dir"]
        if role in seen and seen[role] != adir:
            raise ValueError("роль '%s' с разным advisor_dir (%s vs %s)" % (role, seen[role], adir))
        seen[role] = adir
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
    """Сервер сверяет КАЖДУЮ цитату по ДОВЕРЕННОМУ advisor_dir. Маркеры воркера игнорируются.
    Fail-closed: структурно неверный top-level (argument не str, quotes не list) → ValueError,
    строка изолируется вызывающим (_assemble_role), не сглаживается тихой коэрсией. Внутри списка
    цитат не-dict элемент безопасно пропускается (частичная порча одной цитаты — не всей строки)."""
    arg = raw.get("argument", "")
    if not isinstance(arg, str):
        raise ValueError("argument: ожидалась строка, получено %r" % type(arg).__name__)
    quotes_raw = raw.get("quotes", [])
    if not isinstance(quotes_raw, list):
        raise ValueError("quotes: ожидался список, получено %r" % type(quotes_raw).__name__)
    vq = []
    for q in quotes_raw:
        if not isinstance(q, dict):
            continue
        text = q.get("text", "")
        if not isinstance(text, str):
            text = ""
        fc = verify_fn(text, advisor_dir)
        vq.append({"text": text, "status": fc.get("status", "🟡"),
                   "source": fc.get("source", "")})
    wm = raw.get("worker_model", "")
    if not isinstance(wm, str):
        wm = ""
    return {"argument": arg, "worker_model": wm, "quotes": vq}


def _assemble_role(role, advisor_dir, rows, verify_fn):
    cands = []
    errors = 0
    for r in rows:
        res = r.get("result")
        if not isinstance(res, dict):
            errors += 1                     # битая строка (не dict) — изолируем, сессию не роняем
            continue
        try:
            cands.append(_verify_candidate(res, advisor_dir, verify_fn))
        except Exception:
            errors += 1
    rep = max(cands, key=_judge.score_candidate) if cands else None
    grounded = sum(1 for c in cands if any(q.get("status") == "🔵" for q in c["quotes"]))
    out = {"role": role, "advisor_dir": advisor_dir,
           "representative": rep, "replicas": cands,
           "divergence": _judge.divergence(cands),
           "worker_models": [c["worker_model"] for c in cands],
           "grounded_replicas": grounded,
           "verdict": _judge.verdict(rep)}
    if errors:
        out["errors"] = errors
    return out


def assemble(backend, session_id, verify_fn):
    """Собрать совет: сгруппировать по роли, сервер-сверить верность, сохранить дивергенцию и
    идентичность моделей. verify_fn(quote, advisor_dir)->{status,source} инъектируется (наш гейт).
    diversity: reduced (роль деградировала) | partial (не все реплики сыграны) | full."""
    all_rows = backend.results(session_id, status=None)
    done = [r for r in all_rows if r["status"] == "done"]
    order, meta, total = [], {}, {}
    for r in all_rows:
        role = r["role"]
        if role not in meta:
            meta[role] = r["advisor_dir"]
            order.append(role)
        total[role] = total.get(role, 0) + 1
    roles_out = []
    degraded = []
    all_complete = True
    for role in order:
        rows = [r for r in done if r["role"] == role]
        done_n, total_n = len(rows), total[role]
        if not rows:
            degraded.append(role)
            all_complete = False
            roles_out.append({"role": role, "advisor_dir": meta[role], "degraded": True,
                              "mode": "host_single_brain", "diversity": "reduced",
                              "verdict": "ESCALATE", "representative": None, "replicas": [],
                              "replicas_done": 0, "replicas_total": total_n, "complete": False,
                              "grounded_replicas": 0})
            continue
        role_out = _assemble_role(role, meta[role], rows, verify_fn)
        role_out["replicas_done"] = done_n
        role_out["replicas_total"] = total_n
        role_out["complete"] = done_n == total_n
        if done_n != total_n:
            all_complete = False
        roles_out.append(role_out)
    if degraded:
        diversity = "reduced"
    elif all_complete:
        diversity = "full"
    else:
        diversity = "partial"
    return {"session_id": session_id, "roles": roles_out, "degraded_roles": degraded,
            "diversity": diversity, "complete": all_complete and not degraded}
