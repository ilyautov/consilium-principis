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

from .fidelity import verbatim_in_corpus, best_match  # backend-независимый чек (relative — пакетный стиль)
from corpusbuild.paths import config_path  # единый резолвер пути конфига (fidelity уже положил scripts/ на path)


class StaleIndexError(Exception):
    """Семантический индекс рассинхронизирован с корпусом/моделью/чанкингом/форматом
    (fingerprint в .meta.json не совпал с текущим). Fail-closed: retrieve НЕ отдаёт
    результаты по устаревшему индексу — иначе `source`/цитаты укажут на чанки корпуса,
    которого больше нет, а порог abstain потеряет смысл. `safe_retrieve` ловит и
    деградирует semantic→lexical (наблюдаемо), а не тихо-неверно. Зеркало политики
    load_calibration (staleness через corpus_sha256). НЕ бьёт по verbatim-рву: fidelity
    читает свежий corpus.jsonl напрямую, не .meta.json (см. спека 2026-07-18 §1.1)."""


@dataclass
class Passage:
    text: str
    score: float
    source: str
    # Тир пассажа (P1/P2 первоисточник · S1 комментарий · B аппарат), как он лежит в индексе.
    # None = НЕИЗВЕСТЕН (легаси-индекс/корпус без поля) — трактовать fail-closed, НЕ как
    # первоисточник, иначе поле станет дырой вместо гарда. Ранжирование тир НЕ учитывает:
    # поле сделано видимым для потребителя (cite) и диагностики; политика — отдельное решение.
    tier: str = None


@dataclass
class AbstainResult:
    abstain: bool
    max_score: float
    threshold: float


@dataclass
class FidelityResult:
    status: str       # "🔵" verbatim P1/P2 | "🟢" verbatim S1/S2 (комментарий) | "🟡" экстраполяция
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
        """Tier-aware гейт маркера. Дословный матч сам по себе НЕ даёт 🔵 — решает ТИР:
          P1/P2 → 🔵 (слова автора)
          S1/S2 → 🟢 (дословно, но комментарий — source = комментатор, не голос автора)
          B/A/нет матча/без tier → 🟡 (fail-closed: без провенанса не сертифицируем)."""
        m = best_match(quote, advisor_dir)
        if m is None:
            return FidelityResult(status="🟡", verbatim=False, source="")
        tier, src = m
        if tier in ("P1", "P2"):
            return FidelityResult(status="🔵", verbatim=True, source=src)
        if tier in ("S1", "S2"):
            return FidelityResult(status="🟢", verbatim=True, source=src)
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
    import json
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except Exception:
        return default


_CORPUS_SHA_CACHE = {}  # abspath(corpus.jsonl) -> (mtime_ns, size, sha256)


def corpus_sha256(advisor_dir):
    """sha256 содержимого corpus.jsonl советника (полный hex). ЕДИНЫЙ хэшер для
    калибровки/moat-check (не форкать). Кэш по (mtime_ns, size) — резолюция конфига
    зовёт часто, а корпус меняется только пересборкой. None при ошибке/нет корпуса."""
    import hashlib, os
    try:
        from corpusbuild.paths import corpus_path
        cp = corpus_path(advisor_dir)
        st = os.stat(cp)
        key = os.path.abspath(cp)
        hit = _CORPUS_SHA_CACHE.get(key)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
        h = hashlib.sha256()
        with open(cp, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        sha = h.hexdigest()
        _CORPUS_SHA_CACHE[key] = (st.st_mtime_ns, st.st_size, sha)
        return sha
    except Exception:
        return None


def load_calibration(advisor_dir, validate_corpus=True):
    """Per-advisor калибровка (§3.2 moat-v2): advisors/<slug>/build/calibration.json —
    артефакт сборки (как kernels.json), пишет scripts/calibrate_advisor.py.
    None, если файла нет / бит / calibrated != True (fail-closed → глобальные дефолты).

    STALENESS (review I-2): калибровка валидна только для корпуса, на котором посчитана.
    validate_corpus=True (дефолт — ВСЕ резолюционные пути): stored corpus_sha256 !=
    текущий хэш корпуса ЛИБО поля нет (легаси) → None (fail-closed: устаревшие пороги
    молча не применяются — действуют глобальные дефолты). validate_corpus=False —
    сырой файл для диагностики (doctor показывает «калиброван, но УСТАРЕЛ»)."""
    import json, os
    if not advisor_dir:
        return None
    try:
        from corpusbuild.paths import build_dir
        with open(os.path.join(build_dir(advisor_dir), "calibration.json"),
                  encoding="utf-8") as f:
            cal = json.load(f)
        if not (isinstance(cal, dict) and cal.get("calibrated") is True):
            return None
        if validate_corpus:
            stored = cal.get("corpus_sha256")
            if not stored or stored != corpus_sha256(advisor_dir):
                return None                            # stale / легаси без хэша → fail-closed
        return cal
    except Exception:
        return None


def load_backend_threshold(advisor_dir, backend, default):
    """Порог abstain per backend: per-advisor калибровка (build/calibration.json, §3.2)
    поверх глобального board_config.json / default.

    ОДНОНАПРАВЛЕННОЕ ПРАВИЛО (review I-1): калибровка может только ПОДНЯТЬ порог
    (ужесточить abstention) над значением, которое действовало бы БЕЗ неё (глобальный
    конфиг или default) — возврат max(calibrated, base). Авто-порог из ~24 проб не
    имеет права ОПУСТИТЬ рук-валидированный пол: ниже порог = шире не-abstain зона =
    fail-open. Битое per-advisor значение молча падает на глобальный уровень."""
    import json
    try:
        with open(config_path(), encoding="utf-8") as f:
            at = json.load(f).get("abstain_threshold")
        base = _pick_threshold(at, backend, default)
    except Exception:
        base = default
    cal = load_calibration(advisor_dir)
    if cal:
        try:
            at = cal.get("abstain_threshold")
            if isinstance(at, dict) and backend in at:
                return max(float(at[backend]), base)   # tighten-only floor
        except (TypeError, ValueError):
            pass
    return base


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
    mode = load_config_value("retrieval_mode", "auto")  # auto→semantic при доступном bge-m3 (hybrid = opt-in)
    if prefer == "lexical":
        eng = LexicalEngine()
    elif prefer == "hybrid" or (not prefer and mode == "hybrid" and SemanticEngine.available()):
        from .hybrid import HybridEngine
        eng = HybridEngine()
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
