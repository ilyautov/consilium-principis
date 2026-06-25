"""RemoteEngine — SEAM (не реализован). Форма под будущий хостед-движок: тот же контракт
Engine, ходит по HTTP в endpoint с token. Сейчас только сигнатуры, чтобы remote встал
без переписывания (спека: «под других потом»). auth-логики нет — только параметр token."""
from typing import List, Optional

from . import Engine, Passage   # relative — пакетный стиль


class RemoteEngine(Engine):
    name = "remote"

    def __init__(self, endpoint: Optional[str] = None, token: Optional[str] = None):
        self.endpoint = endpoint
        self.token = token

    @staticmethod
    def available(endpoint: Optional[str] = None) -> bool:
        return bool(endpoint)  # настроен ⇒ доступен (реальный health-check — при реализации)

    def _not_yet(self):
        raise NotImplementedError(
            "RemoteEngine — seam: удалённый движок ещё не реализован. "
            "Настрой endpoint+token и реализуй HTTP-вызовы по MCP_CONTRACT.md.")

    def retrieve(self, question, advisor_dir, top_k=3) -> List[Passage]:
        self._not_yet()

    def build_index(self, advisor_dir):
        self._not_yet()

    def abstain_threshold(self, advisor_dir):
        self._not_yet()
