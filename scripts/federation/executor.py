"""Исполнитель-поверхность: воркер (отдельная сессия) забирает роль-таск, играет советника на
СВОЕЙ модели, кладёт СЫРОГО кандидата. Trust-boundary (заимствование advisor-orchestrator-worker):
бриф — самодостаточные ДАННЫЕ, никогда не интерполируется в shell; воркер маркеры верности НЕ
ставит (их вычисляет наш сервер централизованно на assemble)."""

MAX_ARGUMENT = 8000
MAX_QUOTES = 30
MAX_QUOTE = 2000


def claim_brief(backend, worker_id, roles=None, timeout=1.0):
    """Блокирующий claim → структурный бриф или {'empty': True} по таймауту."""
    c = backend.claim(worker_id, roles=roles, block=True, timeout=timeout)
    if c is None:
        return {"empty": True}
    return {"task_id": c.task_id, "claim_token": c.claim_token,
            "role": c.role, "advisor_dir": c.advisor_dir, "question": c.question}


def heartbeat_task(backend, task_id, worker_id, claim_token):
    """Продлить lease. stale claim_token → {'stale': True}."""
    return backend.heartbeat(task_id, worker_id, claim_token)
