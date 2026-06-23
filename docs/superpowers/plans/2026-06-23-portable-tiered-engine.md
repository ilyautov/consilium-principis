# Portable Tiered Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ввести единую границу `Engine` между скиллом и ретривом, за которой переносимые бэкенды (Lexical 0-install пол / Semantic ollama / Remote seam), с graceful-деградацией, так чтобы защитный контур (fidelity) работал на любом тире.

**Architecture:** In-process адаптер (подход A+C из спеки). Базовый класс `Engine` несёт конкретные `abstain_check` (= max score retrieve < threshold) и `fidelity_check` (substring-матч, backend-независим); бэкенды переопределяют только `retrieve` и `build_index`. `resolve_engine()` детектит возможности и падает вниз semantic→lexical, инвалидируя кэш при runtime-падении. Контракт — MCP-совместимой формы (seam под MCP-фасад/remote).

**Tech Stack:** Python 3 (stdlib для пола; numpy+ollama+Гефест для semantic через существующий `tier_full.py`). Тесты — pytest. Рабочая директория проекта: `personal-board/`. Все команды запускать из неё.

---

## Файловая структура

| Файл | Ответственность |
|---|---|
| `scripts/engine/__init__.py` | контракт: dataclasses `Passage/AbstainResult/FidelityResult`, `Engine` ABC (конкретные abstain/fidelity), `resolve_engine()` |
| `scripts/engine/fidelity.py` | общий verbatim-чек корпуса (backend-независим) |
| `scripts/engine/lexical.py` | `LexicalEngine` — stdlib пол (реюз char-3gram логики) |
| `scripts/engine/semantic.py` | `SemanticEngine` — обёртка `tier_full` |
| `scripts/engine/remote.py` | `RemoteEngine` — заглушка-seam |
| `scripts/doctor.py` | отчёт доступного тира (опц., Task 10) |
| `tests/test_engine_*.py` | юниты контракта/бэкендов/резолвера/деградации |
| `scripts/eval.py` | рефактор: через `resolve_engine` + флаг `--engine` (Task 8) |
| `board_config.json` | хранит `chunk_chars` + `abstain_threshold` per backend (Task 7) |

Существующее переиспользуем: `tier_full.retrieve/build_index/available`, `eval.lexical_retrieve/split_corpus_units/_char_ngrams/norm`.

---

## Task 1: Контракт Engine (dataclasses + ABC + конкретные abstain/fidelity)

**Files:**
- Create: `personal-board/scripts/engine/__init__.py`
- Test: `personal-board/tests/test_engine_contract.py`

- [ ] **Step 1: Failing test — dataclasses и форма abstain/fidelity на фейковом бэкенде**

```python
# personal-board/tests/test_engine_contract.py
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from engine import Engine, Passage, AbstainResult, FidelityResult


class FakeEngine(Engine):
    name = "fake"
    def retrieve(self, question, advisor_dir, top_k=3):
        return [Passage(text="alpha beta", score=0.8, source="x"),
                Passage(text="gamma", score=0.3, source="y")][:top_k]
    def build_index(self, advisor_dir):
        return {}
    def abstain_threshold(self, advisor_dir):
        return 0.5


def test_passage_shape():
    p = Passage(text="t", score=0.1, source="s")
    assert (p.text, p.score, p.source) == ("t", 0.1, "s")

def test_abstain_check_uses_top_score():
    e = FakeEngine()
    r = e.abstain_check("q", "/tmp/adv")
    assert isinstance(r, AbstainResult)
    assert r.abstain is False and r.max_score == 0.8 and r.threshold == 0.5

def test_abstain_when_below_threshold(monkeypatch):
    e = FakeEngine()
    monkeypatch.setattr(e, "retrieve", lambda *a, **k: [Passage("t", 0.2, "s")])
    r = e.abstain_check("q", "/tmp/adv")
    assert r.abstain is True and r.max_score == 0.2
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine'`.

- [ ] **Step 3: Implement contract**

```python
# personal-board/scripts/engine/__init__.py
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
```

- [ ] **Step 4: Run, verify fail на отсутствии fidelity**

Run: `cd personal-board && python3 -m pytest tests/test_engine_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fidelity'` (создадим в Task 2). Это ожидаемо.

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/engine/__init__.py tests/test_engine_contract.py
git commit -m "engine: контракт Engine + dataclasses + конкретные abstain/fidelity"
```

---

## Task 2: fidelity.py — общий verbatim-чек

**Files:**
- Create: `personal-board/scripts/engine/fidelity.py`
- Test: `personal-board/tests/test_engine_fidelity.py`

- [ ] **Step 1: Failing test**

```python
# personal-board/tests/test_engine_fidelity.py
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/ — engine это пакет
from engine.fidelity import verbatim_in_corpus, _norm


def _mk_corpus(tmp, text):
    adv = os.path.join(tmp, "adv")
    os.makedirs(adv, exist_ok=True)
    with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"source": "src.txt", "text": text}, ensure_ascii=False) + "\n")
    return adv


def test_verbatim_hit():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk_corpus(t, "All men are made one for another: teach them better.")
        assert verbatim_in_corpus("teach them better", adv) == "src.txt"

def test_verbatim_miss():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk_corpus(t, "All men are made one for another.")
        assert verbatim_in_corpus("you have power over your mind", adv) is None

def test_norm_collapses_ws_and_punct():
    assert _norm("Teach  them,  better!") == "teach them better"
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_fidelity.py -q`
Expected: FAIL — нет модуля `fidelity`.

- [ ] **Step 3: Implement**

```python
# personal-board/scripts/engine/fidelity.py
"""Backend-независимый verbatim-чек: дословна ли цитата в загруженном корпусе advisor'а.
Это ядро защитного контура — работает даже на 0-install полу (нужен только corpus.jsonl)."""
import os
import re
import json
from typing import Optional


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _corpus_norm_text(advisor_dir: str):
    """Читает corpus.jsonl → список (source, norm_chunk). Терпит отсутствие файла и битые
    JSON-строки. БЕЗ склейки чанков (склейка дала бы кросс-чанковые ложные 🔵 — см. ниже)."""
    path = os.path.join(advisor_dir, "corpus.jsonl")
    chunks = []
    if not os.path.isfile(path):
        return chunks
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            text = rec.get("text") or ""
            src = rec.get("source") or rec.get("citation") or "corpus.jsonl"
            chunks.append((str(src), _norm(text)))
    return chunks


def verbatim_in_corpus(quote: str, advisor_dir: str) -> Optional[str]:
    """Возвращает source ОТДЕЛЬНОГО чанка, где цитата встречается дословно (после
    нормализации), иначе None. Матч — normalized-substring по каждому чанку по отдельности;
    цитата, не найденная ни в одном чанке, → None (caller ставит 🟡). НЕТ склейки чанков:
    она давала бы ложный 🔵 на фразе, случайно совпавшей через границу чанков (худшая ошибка
    для защитного контура). Ошибаемся в безопасную сторону (🟡), не в ложный 🔵."""
    q = _norm(quote)
    if not q:
        return None
    for src, ctext in _corpus_norm_text(advisor_dir):
        if q in ctext:
            return src
    return None
```

> ⚠ Эта версия — ИСПРАВЛЕННАЯ (код-ревью поймал кросс-чанковый ложный 🔵 в первоначальном
> joined-fallback). Регресс-тест `test_no_cross_chunk_false_positive` обязателен.

- [ ] **Step 4: Run fidelity + contract tests (оба зелёные)**

Run: `cd personal-board && python3 -m pytest tests/test_engine_fidelity.py tests/test_engine_contract.py -q`
Expected: PASS (все).

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/engine/fidelity.py tests/test_engine_fidelity.py
git commit -m "engine: общий verbatim-чек (fidelity, backend-независим)"
```

---

## Task 3: LexicalEngine — 0-install пол

**Files:**
- Create: `personal-board/scripts/engine/lexical.py`
- Test: `personal-board/tests/test_engine_lexical.py`

- [ ] **Step 1: Failing test**

```python
# personal-board/tests/test_engine_lexical.py
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/ — engine это пакет
from engine.lexical import LexicalEngine
from engine import Passage


def _mk(tmp, *sentences):
    adv = os.path.join(tmp, "adv")
    os.makedirs(adv, exist_ok=True)
    with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for s in sentences:
            f.write(json.dumps({"source": "src", "text": s}, ensure_ascii=False) + "\n")
    return adv


def test_retrieve_ranks_overlap_first():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, "retire into thyself and be at rest.",
                     "the most compendious way is according to nature.")
        hits = LexicalEngine().retrieve("retire into thyself", adv, top_k=2)
        assert isinstance(hits[0], Passage)
        assert "retire into thyself" in hits[0].text.lower()
        assert hits[0].score >= hits[1].score

def test_build_index_is_noop():
    assert LexicalEngine().build_index("/tmp/whatever") == {}

def test_fidelity_works_on_floor():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, "teach them better or bear with them.")
        r = LexicalEngine().fidelity_check("bear with them", adv)
        assert r.verbatim is True and r.status == "🔵"
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_lexical.py -q`
Expected: FAIL — нет `engine.lexical`.

- [ ] **Step 3: Implement (реюз char-3gram логики, без зависимости от eval.py)**

```python
# personal-board/scripts/engine/lexical.py
"""LexicalEngine — 0-install пол (tier SIMPLE). char-3gram Jaccard вопроса против
предложений корпуса. Никаких внешних зависимостей (stdlib). Порог abstain низкий и
лексический — на кросс-язычных вопросах abstention тут best-effort; жёсткая гарантия —
fidelity (наследуется из базового Engine)."""
import os
import re
import json
from typing import List

from . import Engine, Passage   # relative — пакетный стиль


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _char_ngrams(s: str, n: int = 3):
    s = "  " + _norm(s) + "  "
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _split_units(advisor_dir: str) -> List[str]:
    cj = os.path.join(advisor_dir, "corpus.jsonl")
    if not os.path.isfile(cj):
        return []
    units = []
    for line in open(cj, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            txt = json.loads(line).get("text", "")
        except Exception:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", txt):
            sent = sent.strip()
            if len(sent) >= 8:
                units.append(sent)
    return units


class LexicalEngine(Engine):
    name = "lexical"
    DEFAULT_THRESHOLD = 0.04  # jaccard-скоры малы; калибруется в board_config

    def retrieve(self, question, advisor_dir, top_k=3):
        units = _split_units(advisor_dir)
        qg = _char_ngrams(question)
        if not units or not qg:
            return []
        scored = []
        for u in units:
            ug = _char_ngrams(u)
            union = len(qg | ug) or 1
            scored.append(Passage(text=u, score=len(qg & ug) / union, source="corpus.jsonl"))
        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[:top_k]

    def build_index(self, advisor_dir):
        return {}  # лексике индекс не нужен

    def abstain_threshold(self, advisor_dir):
        from . import load_backend_threshold
        return load_backend_threshold(advisor_dir, self.name, self.DEFAULT_THRESHOLD)
```

- [ ] **Step 4: Добавить `load_backend_threshold` в контракт (минимальный, до Task 7)**

В `personal-board/scripts/engine/__init__.py` добавить функцию (в конец файла):

```python
def _pick_threshold(at, backend, default):
    """Чистая логика выбора порога из значения board_config["abstain_threshold"].
    `at` может быть: dict {backend: value} (новое), число (старый плоский = semantic), None."""
    if isinstance(at, dict):
        return float(at.get(backend, default))
    if isinstance(at, (int, float)) and backend == "semantic":
        return float(at)  # старый плоский порог относился к semantic
    return default


def load_backend_threshold(advisor_dir, backend, default):
    """Порог abstain per backend из board_config.json. Возврат default, если не найдено."""
    import os, json
    # __file__ = .../personal-board/scripts/engine/__init__.py → три dirname до personal-board,
    # где лежит board_config.json (engine на уровень глубже, чем tier_full.py).
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg_path = os.path.join(root, "board_config.json")
    try:
        at = json.load(open(cfg_path, encoding="utf-8")).get("abstain_threshold")
    except Exception:
        return default
    return _pick_threshold(at, backend, default)
```

- [ ] **Step 5: Run lexical tests**

Run: `cd personal-board && python3 -m pytest tests/test_engine_lexical.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd personal-board && git add scripts/engine/lexical.py scripts/engine/__init__.py tests/test_engine_lexical.py
git commit -m "engine: LexicalEngine (0-install пол) + per-backend порог"
```

---

## Task 4: SemanticEngine — обёртка tier_full

**Files:**
- Create: `personal-board/scripts/engine/semantic.py`
- Test: `personal-board/tests/test_engine_semantic.py`

- [ ] **Step 1: Failing test (мокаем tier_full — без живого ollama)**

```python
# personal-board/tests/test_engine_semantic.py
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/


def _fake_tier_full():
    m = types.ModuleType("tier_full")
    m.available = lambda: True
    m.build_index = lambda adv: None
    m.retrieve = lambda q, adv, top_k=3, rerank=False: [
        {"text": "retire into thyself", "score": 0.61, "source": "long.txt"}][:top_k]
    return m


def test_retrieve_maps_to_passages(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("где покой?", "/tmp/adv", top_k=1)
    from engine import Passage
    assert isinstance(hits[0], Passage)
    assert hits[0].score == 0.61 and hits[0].source == "long.txt"

def test_available_reflects_tier_full(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tier_full())
    from engine.semantic import SemanticEngine
    assert SemanticEngine.available() is True
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_semantic.py -q`
Expected: FAIL — нет `engine.semantic`.

- [ ] **Step 3: Implement**

```python
# personal-board/scripts/engine/semantic.py
"""SemanticEngine — обёртка существующего tier_full.py (ollama bge-m3 + Гефест) под
контракт Engine. Логику ретрива НЕ дублирует. Гибридный ретрив — отдельная фаза (Task 9).
tier_full лежит в scripts/ (на уровень выше пакета engine) → импортится top-level."""
from typing import List

from . import Engine, Passage   # relative — пакетный стиль


class SemanticEngine(Engine):
    name = "semantic"
    DEFAULT_THRESHOLD = 0.50  # калиброван на реальном корпусе при chunk_chars=500

    @staticmethod
    def available() -> bool:
        try:
            import tier_full
            return bool(tier_full.available())
        except Exception:
            return False

    def retrieve(self, question, advisor_dir, top_k=3):
        import tier_full
        raw = tier_full.retrieve(question, advisor_dir, top_k=top_k)
        return [Passage(text=d["text"], score=float(d["score"]), source=d["source"]) for d in raw]

    def build_index(self, advisor_dir):
        import tier_full, os
        tier_full.build_index(advisor_dir)
        return {"chunk_chars": int(os.getenv("TIER_CHUNK_CHARS", "500"))}

    def abstain_threshold(self, advisor_dir):
        from . import load_backend_threshold
        return load_backend_threshold(advisor_dir, self.name, self.DEFAULT_THRESHOLD)
```

- [ ] **Step 4: Run semantic tests**

Run: `cd personal-board && python3 -m pytest tests/test_engine_semantic.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/engine/semantic.py tests/test_engine_semantic.py
git commit -m "engine: SemanticEngine (обёртка tier_full) за контрактом"
```

---

## Task 5: resolve_engine — детект, кэш, runtime-деградация

**Files:**
- Modify: `personal-board/scripts/engine/__init__.py` (добавить резолвер)
- Test: `personal-board/tests/test_engine_resolve.py`

- [ ] **Step 1: Failing test**

```python
# personal-board/tests/test_engine_resolve.py
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
import engine as eng
from engine.lexical import LexicalEngine
from engine.semantic import SemanticEngine


def test_falls_to_lexical_when_semantic_unavailable(monkeypatch):
    eng.reset_engine_cache()
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    e = eng.resolve_engine("/tmp/adv")
    assert isinstance(e, LexicalEngine)

def test_picks_semantic_when_available(monkeypatch):
    eng.reset_engine_cache()
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    e = eng.resolve_engine("/tmp/adv")
    assert isinstance(e, SemanticEngine)

def test_runtime_failure_degrades_and_invalidates(monkeypatch):
    eng.reset_engine_cache()
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    def boom(*a, **k):
        raise ConnectionError("ollama died")
    monkeypatch.setattr(SemanticEngine, "retrieve", boom)
    # safe_retrieve должен поймать падение и пере-резолвить вниз
    hits = eng.safe_retrieve("q", "/tmp/adv")  # корпуса нет → lexical вернёт []
    assert hits == []
    assert isinstance(eng.resolve_engine("/tmp/adv"), LexicalEngine)  # кэш инвалидирован вниз
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_resolve.py -q`
Expected: FAIL — нет `resolve_engine/reset_engine_cache/safe_retrieve`.

- [ ] **Step 3: Implement резолвер (добавить в конец `engine/__init__.py`)**

```python
# --- резолвер: детект → кэш per advisor → деградация ---
_ENGINE_CACHE = {}  # advisor_dir -> Engine


def reset_engine_cache():
    _ENGINE_CACHE.clear()


def _advisor_key(advisor_dir):
    import os
    return os.path.abspath(advisor_dir)


def resolve_engine(advisor_dir, prefer: Optional[str] = None) -> Engine:
    """Возвращает лучший доступный бэкенд: remote(настроен) → semantic(ollama) → lexical.
    Кэширует per advisor. prefer='lexical' форсит пол (для eval --engine)."""
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
```

Примечание: ВСЕ импорты внутри пакета — relative (`from .lexical import ...`), потребители держат в sys.path ТОЛЬКО `scripts/` и импортят `engine`/`engine.lexical`. Это исключает дабл-импорт-трап (один и тот же класс, а не два объекта из `lexical` и `engine.lexical`).

- [ ] **Step 4: Run resolver tests**

Run: `cd personal-board && python3 -m pytest tests/test_engine_resolve.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/engine/__init__.py tests/test_engine_resolve.py
git commit -m "engine: resolve_engine + safe_retrieve (детект, кэш, runtime-деградация)"
```

---

## Task 6: Запись chunk_chars↔threshold (лечит баг калибровки)

**Files:**
- Modify: `personal-board/scripts/board_init.py` (писать структуру порога per backend + chunk_chars)
- Test: `personal-board/tests/test_engine_threshold.py`

- [ ] **Step 1: Failing test — load_backend_threshold читает новую структуру**

```python
# personal-board/tests/test_engine_threshold.py
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
from engine import _pick_threshold


def test_dict_form_picks_backend():
    at = {"semantic": 0.5, "lexical": 0.04}
    assert _pick_threshold(at, "semantic", 0.9) == 0.5
    assert _pick_threshold(at, "lexical", 0.9) == 0.04

def test_missing_backend_returns_default():
    assert _pick_threshold({"semantic": 0.5}, "remote", 0.7) == 0.7

def test_legacy_flat_number_maps_to_semantic():
    assert _pick_threshold(0.62, "semantic", 0.5) == 0.62
    assert _pick_threshold(0.62, "lexical", 0.04) == 0.04  # плоский не относится к lexical

def test_none_returns_default():
    assert _pick_threshold(None, "semantic", 0.5) == 0.5
```

> `_pick_threshold` — чистая функция (Task 3), тестируется без файлов. Полный e2e порога — через eval (Task 7) и прогон board_init (ниже).

- [ ] **Step 2: Run — тест чистой логики `_pick_threshold` (реализована в Task 3) зелёный**

Run: `cd personal-board && python3 -m pytest tests/test_engine_threshold.py -q`
Expected: PASS (4 теста). Это регресс на формат board_config; новая работа Task 6 ниже — заставить board_init ПИСАТЬ эту структуру.

- [ ] **Step 3: board_init пишет per-backend порог + chunk_chars**

Найти в `personal-board/scripts/board_init.py` место, где формируется dict для записи в `board_config.json` (ключ `abstain_threshold`). Заменить плоское значение на структуру и добавить `chunk_chars`:

```python
# было: config["abstain_threshold"] = args.abstain_threshold
config["abstain_threshold"] = {
    "semantic": args.abstain_threshold,   # калиброван при chunk_chars ниже
    "lexical": 0.04,                      # лексический пол (best-effort)
}
config["chunk_chars"] = int(os.getenv("TIER_CHUNK_CHARS", "500"))
```

(Если переменной `config` в коде нет — найти словарь, сериализуемый `json.dump(...)` в `board_config.json`, и внести те же два ключа перед записью.)

- [ ] **Step 4: Прогон board_init, проверка структуры**

Run:
```bash
cd personal-board && python3 scripts/board_init.py advisors --semantic-available true >/dev/null
python3 -c "import json; c=json.load(open('board_config.json')); assert isinstance(c['abstain_threshold'],dict) and c['chunk_chars']==500; print('ok', c['abstain_threshold'])"
```
Expected: `ok {'semantic': 0.5, 'lexical': 0.04}`

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/board_init.py board_config.json tests/test_engine_threshold.py
git commit -m "engine: board_config хранит порог per backend + chunk_chars (лечит coupling)"
```

---

## Task 7: Рефактор eval.py на resolve_engine + флаг --engine

**Files:**
- Modify: `personal-board/scripts/eval.py` (retrieve-диспетчер → engine; abstention/fidelity через контракт; argparse `--engine`)
- Test: ручной паритет прогона eval

- [ ] **Step 1: Подключить engine в eval.py**

В шапке `eval.py` после существующих импортов добавить (`HERE` = каталог `scripts/`, уже в sys.path
при запуске `python3 scripts/eval.py`; engine — пакет под scripts/, поэтому НЕ добавляем scripts/engine):

```python
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import engine as _engine
    ENGINE_OK = True
except Exception:
    ENGINE_OK = False
```

- [ ] **Step 2: Заменить тело `retrieve()` на делегирование**

Заменить функцию `retrieve(question, adv_dir, top_k=3)` (строки ~204-213) на:

```python
def retrieve(question, adv_dir, top_k=3):
    """Единая точка: через Engine-контракт (resolve_engine), с graceful-деградацией.
    Fallback на старый лексический путь, если engine-пакет недоступен."""
    if ENGINE_OK:
        prefer = os.getenv("EVAL_ENGINE")  # 'lexical'|'semantic'|None
        eng = _engine.resolve_engine(adv_dir, prefer=prefer)
        try:
            return [{"text": p.text, "score": p.score, "source": p.source}
                    for p in eng.retrieve(question, adv_dir, top_k=top_k)]
        except Exception:
            pass
    return lexical_retrieve(question, adv_dir, top_k=top_k)
```

- [ ] **Step 3: Добавить флаг `--engine` в argparse eval.py**

В разбор аргументов добавить:

```python
ap.add_argument("--engine", choices=["lexical", "semantic"], default=None,
                help="форсить бэкенд (иначе resolved). Прокидывается в EVAL_ENGINE.")
```
и сразу после парса:
```python
if args.engine:
    os.environ["EVAL_ENGINE"] = args.engine
```

- [ ] **Step 4: Паритет — semantic (как раньше) и пол (lexical)**

Run:
```bash
cd personal-board
python3 scripts/eval.py advisors/marcus-aurelius --engine semantic 2>&1 | grep -E "verified|VIOLATION|честных отказов|галлюцинац|tier движка"
python3 scripts/eval.py advisors/marcus-aurelius --engine lexical  2>&1 | grep -E "verified|VIOLATION|честных отказов"
```
Expected: semantic → `🔵 verified 6/6`, `0 VIOLATION`, abstention как до рефактора. lexical → `🔵 verified 6/6` (fidelity backend-независим!), abstention best-effort. Никаких трейсбеков.

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/eval.py
git commit -m "eval: ретрив через resolve_engine + флаг --engine (паритет semantic, fidelity на полу)"
```

---

## Task 8: RemoteEngine seam + зафиксированная MCP-схема

**Files:**
- Create: `personal-board/scripts/engine/remote.py`
- Create: `personal-board/scripts/engine/MCP_CONTRACT.md`
- Test: `personal-board/tests/test_engine_remote.py`

- [ ] **Step 1: Failing test**

```python
# personal-board/tests/test_engine_remote.py
import os, sys, pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
from engine.remote import RemoteEngine


def test_unconfigured_raises_clearly():
    with pytest.raises(NotImplementedError) as e:
        RemoteEngine(endpoint=None, token=None).retrieve("q", "/tmp/adv")
    assert "remote" in str(e.value).lower()

def test_available_false_when_unconfigured():
    assert RemoteEngine.available(endpoint=None) is False
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_remote.py -q`
Expected: FAIL — нет `engine.remote`.

- [ ] **Step 3: Implement seam**

```python
# personal-board/scripts/engine/remote.py
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
```

- [ ] **Step 4: Зафиксировать MCP-схему (документ-контракт)**

```markdown
# personal-board/scripts/engine/MCP_CONTRACT.md
MCP-совместимая форма контракта Engine (для будущего MCP-фасада / RemoteEngine).
Каждый метод = будущий MCP-инструмент с тем же именем и формой ввода/вывода.

- retrieve(question: str, advisor: str, top_k: int=3)
    → [{ text: str, score: float, source: str }]
- abstain_check(question: str, advisor: str)
    → { abstain: bool, max_score: float, threshold: float }
- fidelity_check(quote: str, advisor: str)
    → { status: "🔵"|"🟡", verbatim: bool, source: str }
- build_index(advisor: str)
    → { chunk_chars?: int }

Коллекторы (collect_pd/web/transcript) — отдельная группа build-time инструментов,
не в горячем retrieve-контуре. Добавляются в MCP-фасад при выходе «на других».
```

- [ ] **Step 5: Run remote tests**

Run: `cd personal-board && python3 -m pytest tests/test_engine_remote.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd personal-board && git add scripts/engine/remote.py scripts/engine/MCP_CONTRACT.md tests/test_engine_remote.py
git commit -m "engine: RemoteEngine seam + зафиксированная MCP-схема (не реализуем)"
```

---

## Task 9: (фаза «качество») Гибридный retrieval — фикс thematic-inexact

**Files:**
- Modify: `personal-board/scripts/engine/semantic.py` (гибридная переоценка)
- Test: `personal-board/tests/test_engine_hybrid.py`

- [ ] **Step 1: Failing test — гибрид поднимает пассаж с лексическим совпадением якоря**

```python
# personal-board/tests/test_engine_hybrid.py
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/


def _fake_tf():
    m = types.ModuleType("tier_full")
    m.available = lambda: True
    m.build_index = lambda adv: None
    # семантика ставит «compendious» выше, но якорь запроса дословно в «retire» пассаже
    m.retrieve = lambda q, adv, top_k=3, rerank=False: [
        {"text": "the most compendious way is according to nature", "score": 0.58, "source": "s"},
        {"text": "retire into thyself and be at rest", "score": 0.55, "source": "s"},
    ][:top_k]
    return m


def test_hybrid_lifts_lexical_anchor(monkeypatch):
    monkeypatch.setitem(sys.modules, "tier_full", _fake_tf())
    monkeypatch.setenv("HYBRID_ALPHA", "0.5")
    from engine.semantic import SemanticEngine
    hits = SemanticEngine().retrieve("retire into thyself", "/tmp/adv", top_k=2)
    assert "retire into thyself" in hits[0].text  # гибрид поднял точный пассаж
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_engine_hybrid.py -q`
Expected: FAIL — текущий retrieve отдаёт порядок tier_full (compendious первым).

- [ ] **Step 3: Гибридная переоценка в SemanticEngine.retrieve**

Заменить `SemanticEngine.retrieve` на гибрид (косинус + лексическое перекрытие):

```python
def retrieve(self, question, advisor_dir, top_k=3):
    import os, re, tier_full
    raw = tier_full.retrieve(question, advisor_dir, top_k=max(top_k, int(os.getenv("HYBRID_POOL", "10"))))
    alpha = float(os.getenv("HYBRID_ALPHA", "0.0"))  # 0 = чистая семантика (дефолт безопасный)
    if alpha <= 0:
        return [Passage(d["text"], float(d["score"]), d["source"]) for d in raw[:top_k]]

    def toks(s):
        return set(re.sub(r"[^\w\s]", " ", s.lower()).split())
    qt = toks(question)
    rescored = []
    for d in raw:
        dt = toks(d["text"])
        lex = len(qt & dt) / (len(qt) or 1)
        score = (1 - alpha) * float(d["score"]) + alpha * lex
        rescored.append(Passage(d["text"], score, d["source"]))
    rescored.sort(key=lambda p: p.score, reverse=True)
    return rescored[:top_k]
```

- [ ] **Step 4: Run hybrid test**

Run: `cd personal-board && python3 -m pytest tests/test_engine_hybrid.py -q`
Expected: PASS.

- [ ] **Step 5: Откалибровать alpha на реальном корпусе и зафиксировать**

Run:
```bash
cd personal-board
for a in 0.0 0.3 0.5 0.7; do
  echo "alpha=$a"; HYBRID_ALPHA=$a python3 scripts/eval.py advisors/marcus-aurelius --engine semantic 2>&1 | grep -E "top-1|THEMATIC|честных отказов|галлюцинац"
done
```
Expected: найти alpha, где top-1/top-3 растёт без роста галлюцинаций. Записать лучший в board_config (`"hybrid_alpha": <best>`) и читать его в retrieve вместо env-дефолта. Если ни одна alpha не улучшает — честно оставить 0.0 и зафиксировать в отчёте (как с реранком).

- [ ] **Step 6: Commit**

```bash
cd personal-board && git add scripts/engine/semantic.py tests/test_engine_hybrid.py board_config.json
git commit -m "engine: гибридный retrieval в SemanticEngine (alpha-калибровка thematic-inexact)"
```

---

## Task 10: (опц.) doctor.py — отчёт доступного тира

**Files:**
- Create: `personal-board/scripts/doctor.py`
- Test: `personal-board/tests/test_doctor.py`

- [ ] **Step 1: Failing test**

```python
# personal-board/tests/test_doctor.py
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def test_report_has_tier_line(monkeypatch, capsys):
    from engine.semantic import SemanticEngine
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    import doctor
    doctor.report()
    out = capsys.readouterr().out
    assert "SIMPLE" in out and "ollama" in out
```

- [ ] **Step 2: Run, verify fail**

Run: `cd personal-board && python3 -m pytest tests/test_doctor.py -q`
Expected: FAIL — нет `doctor`.

- [ ] **Step 3: Implement**

```python
# personal-board/scripts/doctor.py
"""Отчёт: какой tier ретрива доступен на этой машине. Помогает «0-install юзеру»
понять, что у него есть, без чтения кода."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/ — engine это пакет


def report():
    from engine.semantic import SemanticEngine
    sem = SemanticEngine.available()
    tier = "FULL (semantic, bge-m3)" if sem else "SIMPLE (lexical floor)"
    print("Consilium-Principis — диагностика движка")
    print(f"  ollama/bge-m3 (semantic): {'✓ доступен' if sem else '✗ нет'}")
    print(f"  → активный tier: {tier}")
    if not sem:
        print("  fidelity-контур: ✓ работает и на полу (verbatim-чек не требует ollama)")
        print("  поднять до FULL: запустить ollama + `ollama pull bge-m3`, затем build_index")


if __name__ == "__main__":
    report()
```

- [ ] **Step 4: Run doctor test + ручной прогон**

Run: `cd personal-board && python3 -m pytest tests/test_doctor.py -q && python3 scripts/doctor.py`
Expected: PASS + человекочитаемый отчёт.

- [ ] **Step 5: Commit**

```bash
cd personal-board && git add scripts/doctor.py tests/test_doctor.py
git commit -m "engine: doctor.py — отчёт доступного тира"
```

---

## Финальный прогон — вся сюита

- [ ] **Все тесты зелёные**

Run: `cd personal-board && python3 -m pytest tests/ -q`
Expected: PASS (все файлы test_engine_*, test_doctor).

- [ ] **Полный eval паритет (resolved + оба форса)**

Run: `cd personal-board && python3 scripts/eval.py advisors/munger advisors/naval advisors/marcus-aurelius 2>&1 | grep -E "verified|VIOLATION|tier движка|честных отказов"`
Expected: fidelity без VIOLATION, tier=FULL при живом ollama, abstention как до миграции.

- [ ] **Обновить SKILL.md** — одна строка про тиры/доктор в секции «Сборка/запуск»:

```
Движок ретрива авто-выбирается (resolve_engine): FULL (ollama bge-m3) если доступен,
иначе SIMPLE-пол (лексика, 0 установки). Защитный контур (fidelity) работает на любом
тире. Диагностика: `python3 scripts/doctor.py`.
```
Commit: `git add SKILL.md && git commit -m "docs: тиры движка + doctor в SKILL.md"`

---

## Заметки по выполнению

- **pytest**: если не установлен — `pip install pytest` (dev-зависимость; runtime-пол остаётся 0-install).
- **sys.path / импорты (важно)**: `engine` — настоящий Python-пакет под `scripts/`. В sys.path кладём ТОЛЬКО `scripts/`; внутри пакета все импорты relative (`from . import ...`, `from .lexical import ...`); потребители импортят `engine`/`engine.lexical`. `tier_full` остаётся top-level модулем в `scripts/` (импортится `import tier_full`, т.к. scripts/ в пути). Это исключает дабл-импорт (когда `lexical` и `engine.lexical` — два разных класс-объекта и `isinstance` ломается).
- **Порядок фаз**: 1→8 — ядро+граница (обязательно). 9 (гибрид) и 10 (doctor) — опциональные/качество, можно отдельной сессией.
- **Гарантия инварианта**: после Task 7 fidelity = 6/6 ОБОИМИ бэкендами. Если lexical даёт VIOLATION — баг в `_corpus_norm_text` (нормализация), не в данных.
```
