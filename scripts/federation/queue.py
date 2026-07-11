"""Субстрат очереди роль-тасков. SQLite single-writer сериализует claim'ы (гонки нет).
Idempotency: per-claim claim_token — ack/nack/heartbeat валидны только с текущим токеном,
поздний ответ реклейменного таска отбрасывается ({stale}). Domain-agnostic: ноль совет-логики."""
import abc
from dataclasses import dataclass


@dataclass
class RoleTask:
    session_id: str
    role: str
    advisor_dir: str
    question: str
    priority: int = 0
    max_attempts: int = 3


@dataclass
class Claim:
    task_id: str
    claim_token: str
    role: str
    advisor_dir: str
    question: str


class QueueBackend(abc.ABC):
    """Шов: SqliteBackend сейчас; RedisBackend/HttpBackend/PostgresBackend (team/corp) позже —
    тот же интерфейс, block=True разблокируется нативным BLPOP/subscribe без правок вызывающих."""

    @abc.abstractmethod
    def enqueue(self, task: RoleTask) -> str: ...

    @abc.abstractmethod
    def claim(self, worker_id: str, roles=None, block: bool = False, timeout: float = 0.0): ...

    @abc.abstractmethod
    def ack(self, task_id: str, worker_id: str, claim_token: str, result: dict) -> dict: ...

    @abc.abstractmethod
    def nack(self, task_id: str, worker_id: str, claim_token: str, error: str) -> dict: ...

    @abc.abstractmethod
    def heartbeat(self, task_id: str, worker_id: str, claim_token: str) -> dict: ...

    @abc.abstractmethod
    def sweep(self, lease_seconds: float) -> int: ...

    @abc.abstractmethod
    def status(self, session_id: str) -> dict: ...
