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


import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")   # управляющие, КРОМЕ \t(09) \n(0a) \r(0d)


def _clean_text(s, maxlen, field):
    """str-проверка + лимит длины (reject) + срез управляющих (sanitize)."""
    if not isinstance(s, str):
        raise ValueError("%s: ожидалась строка" % field)
    if len(s) > maxlen:
        raise ValueError("%s: превышен лимит %d" % (field, maxlen))
    return _CTRL.sub("", s)


def _validate_candidate(cand, worker_model):
    if not isinstance(cand, dict):
        raise ValueError("candidate: ожидался объект")
    if not isinstance(worker_model, str) or not worker_model.strip():
        raise ValueError("worker_model: ожидалась непустая строка")
    argument = _clean_text(cand.get("argument", ""), MAX_ARGUMENT, "argument")
    quotes_in = cand.get("quotes", [])
    if not isinstance(quotes_in, list):
        raise ValueError("quotes: ожидался список")
    if len(quotes_in) > MAX_QUOTES:
        raise ValueError("quotes: превышен лимит %d" % MAX_QUOTES)
    quotes = []
    for i, qd in enumerate(quotes_in):
        if not isinstance(qd, dict):
            raise ValueError("quotes[%d]: ожидался объект" % i)
        quotes.append({"text": _clean_text(qd.get("text", ""), MAX_QUOTE, "quotes[%d].text" % i)})
    return {"argument": argument, "quotes": quotes, "worker_model": worker_model}


def submit_candidate(backend, task_id, worker_id, claim_token, worker_model, candidate):
    """Валидировать сырьё воркера → ack. Маркеры верности НЕ ставим (сервер сверит на assemble).
    Невалидно → {'rejected': причина}; stale claim_token → {'rejected': 'stale ...'}."""
    try:
        result = _validate_candidate(candidate, worker_model)
    except ValueError as e:
        return {"rejected": str(e)}
    ack = backend.ack(task_id, worker_id, claim_token, result)
    if ack.get("stale"):
        return {"rejected": "stale claim_token"}
    return {"ok": True}
