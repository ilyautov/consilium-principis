"""Контракт Engine + резолвер. Граница скилл↔ретрив (спека 2026-06-23, подход A+C).

Базовый класс несёт КОНКРЕТНЫЕ abstain_check и fidelity_check — они backend-независимы:
  • abstain_check = max(retrieve().score) < threshold (fail-closed, arXiv 2404.10960)
  • fidelity_check = дословный substring-матч цитаты в корпусе (verifiable-by-design)
Бэкенды переопределяют только retrieve(), build_index(), abstain_threshold().
Сигнатуры/возвраты — MCP-совместимой формы (seam под MCP-фасад/RemoteEngine).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from .fidelity import verbatim_in_corpus  # backend-независимый чек (relative — пакетный стиль)


@dataclass
class Passage:
    text: str
    score: float
    source: str


@dataclass
class AbstainResult:
    abstain: bool
    max_score: float
    threshold: float


@dataclass
class FidelityResult:
    status: str       # "🔵" verbatim | "🟡" extrapolation
    verbatim: bool
    source: str


class Engine(ABC):
    name = "base"

    @abstractmethod
    def retrieve(self, question: str, advisor_dir: str, top_k: int = 3) -> List[Passage]:
        ...

    @abstractmethod
    def build_index(self, advisor_dir: str) -> dict:
        ...

    @abstractmethod
    def abstain_threshold(self, advisor_dir: str) -> float:
        ...

    # --- backend-независимые ниже ---
    def abstain_check(self, question: str, advisor_dir: str) -> AbstainResult:
        threshold = self.abstain_threshold(advisor_dir)
        hits = self.retrieve(question, advisor_dir, top_k=1)
        max_score = hits[0].score if hits else 0.0
        return AbstainResult(abstain=max_score < threshold,
                             max_score=max_score, threshold=threshold)

    def fidelity_check(self, quote: str, advisor_dir: str) -> FidelityResult:
        src = verbatim_in_corpus(quote, advisor_dir)
        if src:
            return FidelityResult(status="🔵", verbatim=True, source=src)
        return FidelityResult(status="🟡", verbatim=False, source="")
