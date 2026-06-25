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


def _pick_threshold(at, backend, default):
    """Чистая логика выбора порога из значения board_config["abstain_threshold"].
    `at` может быть: dict {backend: value} (новое), число (старый плоский = semantic), None."""
    if isinstance(at, dict):
        return float(at.get(backend, default))
    if isinstance(at, (int, float)) and backend == "semantic":
        return float(at)  # старый плоский порог относился к semantic
    return default


def load_config_value(key, default):
    """Прочитать произвольный ключ из board_config.json (напр. hybrid_alpha). default если нет."""
    import os, json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        with open(os.path.join(root, "board_config.json"), encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except Exception:
        return default


def load_backend_threshold(advisor_dir, backend, default):
    """Порог abstain per backend из board_config.json. Возврат default, если не найдено.
    advisor_dir пока не влияет на выбор (single-repo); зарезервирован под per-advisor конфиг."""
    import os, json
    # __file__ = .../personal-board/scripts/engine/__init__.py → три dirname до корня скилла.
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg_path = os.path.join(root, "board_config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            at = json.load(f).get("abstain_threshold")
    except Exception:
        return default
    return _pick_threshold(at, backend, default)


# --- резолвер: детект → кэш per advisor → деградация ---
_ENGINE_CACHE = {}  # advisor_dir -> Engine


def reset_engine_cache():
    _ENGINE_CACHE.clear()


def _advisor_key(advisor_dir):
    import os
    return os.path.abspath(advisor_dir)


def resolve_engine(advisor_dir, prefer: Optional[str] = None) -> Engine:
    """Возвращает лучший доступный бэкенд: semantic(ollama) → lexical.
    Кэширует per advisor. prefer='lexical'|'semantic' форсит бэкенд (для eval --engine).
    Примечание: вызов с prefer перезаписывает кэш advisor'а выбранным бэкендом
    (ephemeral-форс для eval --engine; в auto-режиме результат кэшируется per advisor)."""
    from .lexical import LexicalEngine
    from .semantic import SemanticEngine
    key = _advisor_key(advisor_dir)
    if key in _ENGINE_CACHE and not prefer:
        return _ENGINE_CACHE[key]
    if prefer == "lexical":
        eng = LexicalEngine()
    elif prefer == "semantic" or SemanticEngine.available():
        eng = SemanticEngine()
    else:
        eng = LexicalEngine()
    _ENGINE_CACHE[key] = eng
    return eng


def _degrade(advisor_dir):
    """Сбросить semantic→lexical для advisor (после runtime-падения)."""
    from .lexical import LexicalEngine
    _ENGINE_CACHE[_advisor_key(advisor_dir)] = LexicalEngine()


def safe_retrieve(question, advisor_dir, top_k=3) -> List[Passage]:
    """retrieve с graceful-деградацией: при падении бэкенда инвалидирует кэш вниз и
    повторяет на lexical. «never crash» mid-session."""
    eng = resolve_engine(advisor_dir)
    try:
        return eng.retrieve(question, advisor_dir, top_k=top_k)
    except Exception:
        _degrade(advisor_dir)
        return resolve_engine(advisor_dir).retrieve(question, advisor_dir, top_k=top_k)
