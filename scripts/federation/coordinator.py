"""Координатор совета-федерации: разложить план в роль-таски (по N реплик на роль), опросить статус,
собрать кандидатов. Верность сверяет НАШ сервер централизованно (позже)."""
from federation.queue import RoleTask


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
