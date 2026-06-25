# Генеративный мост P1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить провенанс-граф над tier-aware корпусом (S1→P1 кросс-язычные линки, заземлённые кернелы, calibrated enrichment, weakest-link маркер) и фальсифицируемо проверить мост (Exp A) и рёбра графа.

**Architecture:** Один граф; три производителя рёбер (`link`, `kernels`, `enrich`) пишут артефакты в `build/`, `graph` их унифицирует и даёт чистую `weakest_link(path)`. Маркер ответа = слабейшее звено на трассе. Pure-функции юнит-тестируемы без LLM; оркестраторы дёргают ollama. Спека: `docs/superpowers/specs/2026-06-25-generative-bridge-p1.md`.

**Tech Stack:** Python 3.11, pytest, ollama (bge-m3 эмбеддинги через `/api/embed`, gemma3:27b генерация через `/api/generate`), существующий пакет `scripts/corpusbuild/`.

---

## Файловая структура

| Файл | Ответственность |
|------|-----------------|
| `advisors/machiavelli/sources/manifest.json` (mod) | регионы: интро переводчиков → B |
| `scripts/corpusbuild/ids.py` (new) | `chunk_id(rec)`, `load_corpus(advisor_dir)` |
| `scripts/corpusbuild/embed.py` (new) | `cosine(a,b)`, `embed_texts(texts)` (ollama) |
| `scripts/corpusbuild/link.py` (new) | `nearest_p1(...)` (pure), `build_links(advisor_dir)` |
| `scripts/corpusbuild/kernels.py` (new) | `ground_kernels(...)` (pure), `build_kernels(advisor_dir)` |
| `scripts/corpusbuild/enrich.py` (new) | `make_enrichment_record(...)` (invariants), `build_enrichment(advisor_dir)` |
| `scripts/corpusbuild/graph.py` (new) | `marker_of(node)`, `weakest_link(path)` (pure), `assemble_graph(advisor_dir)` |
| `scripts/engine/fidelity.py` (mod) | `marker_for_path(path, advisor_dir)` |
| `scripts/corpusbuild/doctor.py` (mod) | калибровочные инварианты + region-preview |
| `scripts/exp_bridge.py` (new) | Эксперимент A (мост-recall) |
| `scripts/exp_graph.py` (new) | граф-валидация (рёбра не галлюцинированы) |

Все юнит-тесты — в `tests/`, импорт через `sys.path.insert(0, ".../scripts")` + `from corpusbuild import …` / `from engine import …` (как в существующих тестах).

---

### Task 1: P0.5 — регионы Макиавелли + пересборка

**Files:**
- Modify: `advisors/machiavelli/sources/manifest.json`
- (операционная задача — данные + пересборка, не TDD)

- [ ] **Step 1: Найти границы тела в обоих источниках**

Run:
```bash
cd ~/personal/Projects/personal-board-skill-2026-06-10
grep -nE "^[A-Z][A-Z .,'\"-]{6,}$" advisors/machiavelli/sources/the-prince-marriott.txt | head -20
grep -nE "^[A-Z][A-Z .,'\"-]{6,}$" advisors/machiavelli/sources/discourses-livy-thomson.txt | head -25
grep -nE "FOOTNOTES|^NOTES|^APPENDIX|END OF (THE )?(PROJECT )?GUTENBERG|TRANSCRIBER" advisors/machiavelli/sources/the-prince-marriott.txt | head
grep -nE "FOOTNOTES|^NOTES|^APPENDIX|END OF (THE )?(PROJECT )?GUTENBERG|TRANSCRIBER" advisors/machiavelli/sources/discourses-livy-thomson.txt | head
```

Правило выбора маркеров (СЕКВЕНЦИАЛЬНЫЕ регионы, различимые строки):
- `from` тела P1 = первый заголовок, начинающий слова Макиавелли (для Prince это `DEDICATION` — собственное посвящение Макиавелли Лоренцо, ~стр.469; интро Marriott `INTRODUCTION`/`THE MAN AND HIS WORKS` выше → B).
- хвост S1 = первый маркер примечаний/конца (`FOOTNOTES`/`END OF`/`TRANSCRIBER`), если есть.
- Для Discourses выбрать аналогичный заголовок начала тела по выводу grep (напр. `THE FIRST BOOK`/`CHAPTER I`/`PREFACE` — preface Макиавелли = P1).

- [ ] **Step 2: Прописать regions в манифесте**

Отредактировать `advisors/machiavelli/sources/manifest.json`: добавить ключ `"regions"` в записи `the-prince-marriott.txt` и `discourses-livy-thomson.txt`. Формат (подставить реальные маркеры из Step 1):
```json
"the-prince-marriott.txt": {
  "tier": "P1", "attribution": "Niccolò Machiavelli", "title": "The Prince",
  "translator": "W. K. Marriott", "lang": "en", "license": "public-domain",
  "regions": [
    {"tier": "B",  "until": "DEDICATION"},
    {"tier": "P1", "from": "DEDICATION", "until": "FOOTNOTES"},
    {"tier": "S1", "from": "FOOTNOTES"}
  ]
}
```
(Если хвостового маркера нет — оставить только два региона B→P1 без последнего S1.) Тарасов-запись НЕ трогать.

- [ ] **Step 3: Пересобрать и проверить распределение глазами**

Run:
```bash
python3 scripts/corpus_build.py advisors/machiavelli
python3 - <<'PY'
import json
ch=[json.loads(l) for l in open("advisors/machiavelli/build/corpus.jsonl",encoding="utf-8")]
from collections import Counter
print(Counter((c["source"][:14], c["tier"]) for c in ch))
# первый P1-чанк Prince ДОЛЖЕН быть словами Макиавелли (не Marriott)
p1=[c for c in ch if "prince" in c["source"] and c["tier"]=="P1"]
print("первый P1 Prince:", p1[0]["text"][:160].replace(chr(10)," "))
PY
```
Expected: доктор `✓ OK`; первый P1-чанк Prince — посвящение/глава Макиавелли («To the Magnificent…»/«All states…»), НЕ «The little book suffered many vicissitudes» (это был Marriott). Если первый P1 всё ещё Marriott — маркер `from` неверен, вернуться к Step 1.

- [ ] **Step 4: Пересобрать семантический индекс (текст P1 изменился — интро ушло в B)**

Run: `python3 scripts/tier_full.py advisors/machiavelli`
Expected: завершается без ошибок, `data/embeddings_machiavelli.*` обновлены.

- [ ] **Step 5: Commit**

```bash
git add advisors/machiavelli/sources/manifest.json
git commit -m "machiavelli: регионы манифеста — интро переводчиков Marriott/Thomson → B (чистка front-matter)"
```
(Манифест НЕ gitignored — он трекается; Тарасов-txt и build/ остаются gitignored.) Добавить тело-строку `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 2: `ids.py` — стабильный chunk_id и загрузка корпуса

**Files:**
- Create: `scripts/corpusbuild/ids.py`
- Test: `tests/test_corpus_ids.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_ids.py`:
```python
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import ids

def test_chunk_id_is_source_and_line_span():
    rec = {"source": "the-prince.txt", "tier": "P1", "start": ["line", 469], "end": ["line", 520], "text": "x"}
    assert ids.chunk_id(rec) == "the-prince.txt:469-520"

def test_load_corpus_reads_build(tmp_path):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    rows = [{"source": "p.txt", "tier": "P1", "start": ["line", 1], "end": ["line", 9], "text": "hi"}]
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(rows[0]) + "\n")
    got = ids.load_corpus(str(adv))
    assert len(got) == 1 and got[0]["id"] == "p.txt:1-9"
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_corpus_ids.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement** `scripts/corpusbuild/ids.py`:
```python
"""Стабильные идентификаторы узлов графа и загрузка корпуса."""
import json
from . import paths


def chunk_id(rec: dict) -> str:
    """Детерминированный id чанка = source:startline-endline."""
    return f'{rec["source"]}:{rec["start"][1]}-{rec["end"][1]}'


def load_corpus(advisor_dir: str) -> list:
    """Читает build/corpus.jsonl, добавляет каждому записи поле 'id'."""
    out = []
    with open(paths.corpus_path(advisor_dir), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                rec["id"] = chunk_id(rec)
                out.append(rec)
    return out
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_corpus_ids.py -v` (2 passed), затем `python3 -m pytest tests/ -q` (зелёный).

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/ids.py tests/test_corpus_ids.py
git commit -m "corpus: ids — стабильный chunk_id + load_corpus"
```
(+ `Co-Authored-By:` строка.)

---

### Task 3: `embed.py` — косинус и эмбеддинги

**Files:**
- Create: `scripts/corpusbuild/embed.py`
- Test: `tests/test_corpus_embed.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_embed.py`:
```python
import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import embed

def test_cosine_orthogonal_and_identical():
    assert abs(embed.cosine([1.0, 0.0], [0.0, 1.0]) - 0.0) < 1e-9
    assert abs(embed.cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9

def test_cosine_is_normalized():
    # ненормированные входы → косинус, не сырой dot
    assert abs(embed.cosine([3.0, 0.0], [5.0, 0.0]) - 1.0) < 1e-9
```

- [ ] **Step 2: Run, expect FAIL** — ModuleNotFoundError.

- [ ] **Step 3: Implement** `scripts/corpusbuild/embed.py`:
```python
"""Эмбеддинги (bge-m3 через ollama) и косинус. Косинус — чистый, юнит-тестируем без сети."""
import os, json, math, urllib.request

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")


def cosine(a, b) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def embed_texts(texts, batch: int = 64) -> list:
    """Возвращает НОРМИРОВАННЫЕ векторы для texts (bge-m3, многоязычный)."""
    out = []
    for i in range(0, len(texts), batch):
        body = json.dumps({"model": EMBED_MODEL, "input": texts[i:i + batch]}).encode()
        req = urllib.request.Request(f"{OLLAMA}/api/embed", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            out.extend(json.loads(r.read())["embeddings"])
    norm = []
    for v in out:
        s = math.sqrt(sum(x * x for x in v)) or 1.0
        norm.append([x / s for x in v])
    return norm
```

- [ ] **Step 4: Run, expect PASS** (3 passed) + full suite зелёный.

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/embed.py tests/test_corpus_embed.py
git commit -m "corpus: embed — bge-m3 эмбеддинги + чистый косинус"
```

---

### Task 4: `link.py` — S1→P1 кросс-язычный мост

**Files:**
- Create: `scripts/corpusbuild/link.py`
- Test: `tests/test_corpus_link.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_link.py`:
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import link

def test_nearest_p1_picks_above_threshold_topm():
    s1 = ("t.txt:1-2", [1.0, 0.0])
    p1 = [("a:1-2", [0.99, 0.14]), ("b:3-4", [0.0, 1.0]), ("c:5-6", [0.95, 0.31])]
    links = link.nearest_p1(s1, p1, top_m=2, min_cos=0.5)
    dsts = [l["dst"] for l in links]
    assert dsts == ["a:1-2", "c:5-6"]          # два самых близких выше порога, по убыванию
    assert all(l["src"] == "t.txt:1-2" and l["type"] == "толкует" for l in links)

def test_nearest_p1_drops_below_threshold():
    s1 = ("t.txt:1-2", [1.0, 0.0])
    p1 = [("b:3-4", [0.0, 1.0])]               # ортогонален → cos 0 < порог
    assert link.nearest_p1(s1, p1, top_m=3, min_cos=0.45) == []
```

- [ ] **Step 2: Run, expect FAIL** — ModuleNotFoundError.

- [ ] **Step 3: Implement** `scripts/corpusbuild/link.py`:
```python
"""S1→P1 кросс-язычный семантический мост (русский Тарасов → английский Макиавелли).
nearest_p1 — чистая (тестируема без сети); build_links эмбеддит и зовёт её."""
import json
from . import embed, ids, paths


def nearest_p1(s1, p1, top_m: int = 3, min_cos: float = 0.45) -> list:
    """s1=(id, vec); p1=[(id, vec)…]. Возвращает ≤top_m рёбер выше порога, по убыванию косинуса."""
    sid, svec = s1
    scored = [(pid, embed.cosine(svec, pvec)) for pid, pvec in p1]
    scored = [(pid, c) for pid, c in scored if c >= min_cos]
    scored.sort(key=lambda t: -t[1])
    return [{"src": sid, "dst": pid, "type": "толкует", "weight": round(c, 4), "cross_lingual": True}
            for pid, c in scored[:top_m]]


def build_links(advisor_dir: str, top_m: int = 3, min_cos: float = 0.45) -> list:
    """Эмбеддит P1- и S1-чанки, строит links.jsonl. Возвращает все рёбра."""
    corpus = ids.load_corpus(advisor_dir)
    p1c = [c for c in corpus if c["tier"] in ("P1", "P2")]
    s1c = [c for c in corpus if c["tier"] in ("S1", "S2")]
    p1vec = embed.embed_texts([c["text"] for c in p1c])
    s1vec = embed.embed_texts([c["text"] for c in s1c])
    p1 = list(zip([c["id"] for c in p1c], p1vec))
    links = []
    for c, v in zip(s1c, s1vec):
        links.extend(nearest_p1((c["id"], v), p1, top_m, min_cos))
    out = f"{paths.build_dir(advisor_dir)}/links.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for l in links:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    print(f"[link] {advisor_dir}: {len(links)} рёбер S1→P1 (из {len(s1c)} S1-чанков) → {out}")
    return links
```
(Примечание: `paths.build_dir(advisor_dir)` уже существует из P0.)

- [ ] **Step 4: Run, expect PASS** (2 passed) + full suite зелёный. (build_links дёргает ollama — НЕ в юните; smoke в Task 10.)

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/link.py tests/test_corpus_link.py
git commit -m "corpus: link — S1→P1 кросс-язычный семантический мост (порог + top-m)"
```

---

### Task 5: `kernels.py` — извлечь и заземлить кернелы

**Files:**
- Create: `scripts/corpusbuild/kernels.py`
- Test: `tests/test_corpus_kernels.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_kernels.py`:
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import kernels

def test_ground_kernel_keeps_topn_above_threshold():
    kvec = [1.0, 0.0]
    p1 = [("a:1-2", [0.99, 0.14]), ("b:3-4", [0.0, 1.0]), ("c:5-6", [0.95, 0.31])]
    g = kernels.ground_kernel(kvec, p1, ground_n=2, min_cos=0.5)
    assert g == ["a:1-2", "c:5-6"]

def test_groundless_kernel_returns_empty():
    kvec = [1.0, 0.0]
    p1 = [("b:3-4", [0.0, 1.0])]               # ничего выше порога
    assert kernels.ground_kernel(kvec, p1, ground_n=3, min_cos=0.45) == []

def test_assemble_drops_groundless():
    # L2.3.1: безземельный кернел не существует
    items = [{"name": "K1", "method": "m", "grounded_in": ["a:1-2"]},
             {"name": "K2", "method": "m", "grounded_in": []}]
    kept = kernels.drop_groundless(items)
    assert [k["name"] for k in kept] == ["K1"]
```

- [ ] **Step 2: Run, expect FAIL** — ModuleNotFoundError.

- [ ] **Step 3: Implement** `scripts/corpusbuild/kernels.py`:
```python
"""Извлечь мета-идеи (кернелы) и ЗАЗЕМЛИТЬ их к P1-пассажам. L2.3.1: безземельный кернел не существует.
Экстракция переиспользует уже фальсиф-валидную логику exp_kernels (отдельный скрипт). ground_kernel /
drop_groundless — чистые, тестируемы без сети."""
import json
from . import embed, ids, paths


def ground_kernel(kvec, p1, ground_n: int = 5, min_cos: float = 0.45) -> list:
    """Топ-N ближайших P1-id выше порога. p1=[(id, vec)…]."""
    scored = [(pid, embed.cosine(kvec, pvec)) for pid, pvec in p1]
    scored = [(pid, c) for pid, c in scored if c >= min_cos]
    scored.sort(key=lambda t: -t[1])
    return [pid for pid, _ in scored[:ground_n]]


def drop_groundless(items: list) -> list:
    """Выкинуть кернелы без заземления (L2.3.1)."""
    return [k for k in items if k.get("grounded_in")]


def build_kernels(advisor_dir: str, author: str, k: int = 6, ground_n: int = 5, min_cos: float = 0.45) -> list:
    """extract (gemma) → embed → ground → drop groundless → kernels.json."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/ на путь
    from exp_kernels import extract_kernels  # уже валидная экстракция
    corpus = ids.load_corpus(advisor_dir)
    p1c = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c.get("text", "")) > 250]
    names = extract_kernels(author, [{"text": c["text"]} for c in p1c], k=k)
    kvecs = embed.embed_texts(names)
    p1vec = embed.embed_texts([c["text"] for c in p1c])
    p1 = list(zip([c["id"] for c in p1c], p1vec))
    items = [{"name": n, "method": n, "grounded_in": ground_kernel(kv, p1, ground_n, min_cos)}
             for n, kv in zip(names, kvecs)]
    items = drop_groundless(items)
    out = f"{paths.build_dir(advisor_dir)}/kernels.json"
    json.dump(items, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[kernels] {advisor_dir}: {len(items)} заземлённых кернелов → {out}")
    return items
```

- [ ] **Step 4: Run, expect PASS** (3 passed) + full suite зелёный.

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/kernels.py tests/test_corpus_kernels.py
git commit -m "corpus: kernels — извлечение + заземление к P1, выброс безземельных (L2.3.1)"
```

---

### Task 6: `enrich.py` — calibrated enrichment

**Files:**
- Create: `scripts/corpusbuild/enrich.py`
- Test: `tests/test_corpus_enrich.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_enrich.py`:
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import enrich
import pytest

def test_enrichment_record_is_derived_never_quote():
    r = enrich.make_enrichment_record("пример", "текст", derived_from=["p:1-2"])
    assert r["tier"] == "derived" and r["never_quote"] is True
    assert r["kind"] == "пример" and r["derived_from"] == ["p:1-2"]

def test_cross_domain_requires_kernel_trace():
    # L2.3.2: кросс-домен ВСЕГДА должен трассироваться к кернелу
    with pytest.raises(ValueError):
        enrich.make_enrichment_record("кросс-домен", "t", derived_from=["p:1-2"], traces_to_kernel=None)
    ok = enrich.make_enrichment_record("кросс-домен", "t", derived_from=["p:1-2"], traces_to_kernel="K1")
    assert ok["traces_to_kernel"] == "K1"
```

- [ ] **Step 2: Run, expect FAIL** — ModuleNotFoundError.

- [ ] **Step 3: Implement** `scripts/corpusbuild/enrich.py`:
```python
"""Калиброванный enrichment: LLM-расшифровка P1 в примеры/ситуации/кросс-домен/осовременивание.
Всегда derived+never_quote, trace к источнику. L2.3.2: кросс-домен обязан трассироваться к кернелу.
make_enrichment_record — чистая, юнит-гейт инвариантов."""
import json
from . import ids, paths

KINDS = ["пример", "ситуация", "кросс-домен", "осовременивание"]


def make_enrichment_record(kind: str, text: str, derived_from: list, traces_to_kernel: str = None) -> dict:
    if kind == "кросс-домен" and not traces_to_kernel:
        raise ValueError("кросс-домен обязан трассироваться к кернелу (L2.3.2)")
    rec = {"kind": kind, "text": text, "derived_from": list(derived_from),
           "tier": "derived", "never_quote": True}
    if traces_to_kernel:
        rec["traces_to_kernel"] = traces_to_kernel
    return rec


def _generate(text: str, kind: str) -> str:
    """LLM-расшифровка одного P1-пассажа в один enrichment-текст (gemma)."""
    import os, urllib.request
    ollama = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.getenv("KERNEL_MODEL", "gemma3:27b")
    prompt = (f"Пассаж первоисточника:\n{text[:800]}\n\n"
              f"Дай ОДНО краткое «{kind}» (1-3 предложения), раскрывающее идею пассажа для современного "
              f"читателя. Не цитируй дословно — это производный текст.")
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.5}}).encode()
    req = urllib.request.Request(f"{ollama}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=420) as r:
        return json.loads(r.read()).get("response", "").strip()


def build_enrichment(advisor_dir: str, kinds=None, limit: int = 60) -> list:
    """Генерит enrichment для сэмпла P1-пассажей. kinds=пример/ситуация по умолчанию (кросс-домен —
    отдельным проходом с привязкой к кернелу, см. exp; здесь базовые)."""
    kinds = kinds or ["пример", "ситуация"]
    corpus = ids.load_corpus(advisor_dir)
    p1c = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c.get("text", "")) > 300]
    step = max(1, len(p1c) // limit)
    sample = p1c[::step][:limit]
    out_recs = []
    for c in sample:
        for kind in kinds:
            txt = _generate(c["text"], kind)
            if txt:
                out_recs.append(make_enrichment_record(kind, txt, derived_from=[c["id"]]))
    out = f"{paths.build_dir(advisor_dir)}/enrichment.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in out_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[enrich] {advisor_dir}: {len(out_recs)} derived-записей → {out}")
    return out_recs
```

- [ ] **Step 4: Run, expect PASS** (2 passed) + full suite зелёный.

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/enrich.py tests/test_corpus_enrich.py
git commit -m "corpus: enrich — derived+never_quote, кросс-домен→trace к кернелу (L2.3.2)"
```

---

### Task 7: `graph.py` — сборка + правило слабого звена

**Files:**
- Create: `scripts/corpusbuild/graph.py`
- Test: `tests/test_corpus_graph.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_graph.py`:
```python
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import graph

def test_marker_of_by_kind():
    assert graph.marker_of({"kind": "p1"}) == "🔵"
    assert graph.marker_of({"kind": "kernel"}) == "🔵"
    assert graph.marker_of({"kind": "s1"}) == "🟢"
    assert graph.marker_of({"kind": "enrichment"}) == "🟡"
    assert graph.marker_of({"kind": "что-то-неизвестное"}) == "🟡"   # fail-closed = слабейшее

def test_weakest_link_returns_weakest_on_path():
    pure_blue = [{"kind": "p1"}, {"kind": "kernel"}]
    assert graph.weakest_link(pure_blue) == "🔵"
    via_green = [{"kind": "p1"}, {"kind": "s1"}]
    assert graph.weakest_link(via_green) == "🟢"
    via_yellow = [{"kind": "p1"}, {"kind": "s1"}, {"kind": "cross_domain"}]
    assert graph.weakest_link(via_yellow) == "🟡"

def test_assemble_graph_unifies_edges(tmp_path):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "links.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"src": "t:1-2", "dst": "p:3-4", "type": "толкует", "weight": 0.6}) + "\n")
    with open(adv / "build" / "kernels.json", "w", encoding="utf-8") as f:
        json.dump([{"name": "K1", "grounded_in": ["p:3-4"]}], f)
    edges = graph.assemble_graph(str(adv))
    types = {e["type"] for e in edges}
    assert "толкует" in types and "заземляет" in types
```

- [ ] **Step 2: Run, expect FAIL** — ModuleNotFoundError.

- [ ] **Step 3: Implement** `scripts/corpusbuild/graph.py`:
```python
"""Сборка графа провенанса и правило слабого звена (L2.2).
marker_of / weakest_link — чистые, ядро контура на трассе."""
import json, os
from . import paths

# 🔵 сильнее 🟢 сильнее 🟡; ранг = «слабость»
_RANK = {"🔵": 0, "🟢": 1, "🟡": 2}
_BLUE = {"p1", "p2", "kernel"}
_GREEN = {"s1", "s2", "толкование"}


def marker_of(node: dict) -> str:
    kind = node.get("kind", "")
    if kind in _BLUE:
        return "🔵"
    if kind in _GREEN:
        return "🟢"
    return "🟡"   # enrichment/cross_domain/user/неизвестное → fail-closed слабейшее


def weakest_link(path: list) -> str:
    """Маркер составного ответа = самое слабое звено на пути по графу."""
    if not path:
        return "🟡"
    return max((marker_of(n) for n in path), key=lambda m: _RANK[m])


def assemble_graph(advisor_dir: str) -> list:
    """Унифицирует links.jsonl (толкует) + kernels.json (заземляет) + enrichment.jsonl (раскрывает)
    в graph.jsonl как {src_id, dst_id, type, weight}."""
    bd = paths.build_dir(advisor_dir)
    edges = []
    lp = os.path.join(bd, "links.jsonl")
    if os.path.isfile(lp):
        with open(lp, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    l = json.loads(line)
                    edges.append({"src_id": l["src"], "dst_id": l["dst"],
                                  "type": "толкует", "weight": l.get("weight", 0.0)})
    kp = os.path.join(bd, "kernels.json")
    if os.path.isfile(kp):
        for k in json.load(open(kp, encoding="utf-8")):
            for pid in k.get("grounded_in", []):
                edges.append({"src_id": k["name"], "dst_id": pid, "type": "заземляет", "weight": 1.0})
    ep = os.path.join(bd, "enrichment.jsonl")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip():
                    e = json.loads(line)
                    for pid in e.get("derived_from", []):
                        edges.append({"src_id": f'enrich:{i}', "dst_id": pid,
                                      "type": "раскрывает", "weight": 1.0})
    out = os.path.join(bd, "graph.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for e in edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"[graph] {advisor_dir}: {len(edges)} рёбер → {out}")
    return edges
```

- [ ] **Step 4: Run, expect PASS** (3 passed) + full suite зелёный.

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/graph.py tests/test_corpus_graph.py
git commit -m "corpus: graph — сборка рёбер + правило слабого звена (маркер с трассы, L2.2)"
```

---

### Task 8: fidelity — маркер с трассы по графу

**Files:**
- Modify: `scripts/engine/fidelity.py` (ADD-only)
- Test: `tests/test_fidelity_marker.py`

- [ ] **Step 1: Failing test** `tests/test_fidelity_marker.py`:
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from engine import fidelity

def test_marker_for_path_wraps_weakest_link():
    assert fidelity.marker_for_path([{"kind": "p1"}, {"kind": "kernel"}]) == "🔵"
    assert fidelity.marker_for_path([{"kind": "p1"}, {"kind": "cross_domain"}]) == "🟡"
```

- [ ] **Step 2: Run, expect FAIL** — AttributeError: no attribute 'marker_for_path'.

- [ ] **Step 3: Implement** — добавить В КОНЕЦ `scripts/engine/fidelity.py` (ничего существующего не менять). Импорт `graph` лениво, чтобы не тянуть corpusbuild на каждом импорте fidelity:
```python
def marker_for_path(path, advisor_dir: str = None) -> str:
    """Маркер составного ответа = слабейшее звено на его трассе по графу (L2.2).
    Нижний слой 🔵 остаётся вербатим-гейтом (is_blue_eligible)."""
    from corpusbuild import graph
    return graph.weakest_link(path)
```
(`advisor_dir` пока не используется — зарезервирован под будущую проверку заземления узлов; оставить в сигнатуре для стабильности интерфейса.)

- [ ] **Step 4: Run, expect PASS** (2 passed) + full suite зелёный (особенно существующие fidelity-тесты).

- [ ] **Step 5: Commit**
```bash
git add scripts/engine/fidelity.py tests/test_fidelity_marker.py
git commit -m "fidelity: marker_for_path — маркер ответа с трассы по графу (обёртка weakest_link)"
```

---

### Task 9: doctor — калибровочные инварианты + region-preview

**Files:**
- Modify: `scripts/corpusbuild/doctor.py`
- Test: `tests/test_corpus_doctor_calib.py`

- [ ] **Step 1: Failing test** `tests/test_corpus_doctor_calib.py`:
```python
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import doctor

def _build(adv, corpus_rows, kernels=None, enrich=None):
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in corpus_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if kernels is not None:
        json.dump(kernels, open(os.path.join(adv, "build", "kernels.json"), "w"))
    if enrich is not None:
        with open(os.path.join(adv, "build", "enrichment.jsonl"), "w", encoding="utf-8") as f:
            for r in enrich:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

def test_calibration_flags_groundless_kernel(tmp_path):
    adv = str(tmp_path)
    _build(adv, [{"source": "p", "tier": "P1", "text": "ok"}],
           kernels=[{"name": "K", "grounded_in": []}])
    rep = doctor.calibration(adv)
    assert rep["groundless_kernels"] == 1 and rep["ok"] is False

def test_calibration_flags_crossdomain_without_trace(tmp_path):
    adv = str(tmp_path)
    _build(adv, [{"source": "p", "tier": "P1", "text": "ok"}],
           enrich=[{"kind": "кросс-домен", "text": "t", "derived_from": ["p:1-1"], "tier": "derived"}])
    rep = doctor.calibration(adv)
    assert rep["untraced_cross_domain"] == 1 and rep["ok"] is False

def test_calibration_ok_when_clean(tmp_path):
    adv = str(tmp_path)
    _build(adv, [{"source": "p", "tier": "P1", "text": "ok"}],
           kernels=[{"name": "K", "grounded_in": ["p:1-1"]}],
           enrich=[{"kind": "пример", "text": "t", "derived_from": ["p:1-1"], "tier": "derived"}])
    assert doctor.calibration(adv)["ok"] is True
```

- [ ] **Step 2: Run, expect FAIL** — AttributeError: no attribute 'calibration'.

- [ ] **Step 3: Implement** — добавить в `scripts/corpusbuild/doctor.py` функцию `calibration` (существующую `report` не менять):
```python
def calibration(advisor_dir: str) -> dict:
    """Калибровочные инварианты графа (L2.3): нет безземельных кернелов; кросс-домен-enrichment
    обязан иметь traces_to_kernel. Возвращает {ok, groundless_kernels, untraced_cross_domain}."""
    import os
    from . import paths
    bd = paths.build_dir(advisor_dir)
    groundless = 0
    kp = os.path.join(bd, "kernels.json")
    if os.path.isfile(kp):
        groundless = sum(1 for k in json.load(open(kp, encoding="utf-8")) if not k.get("grounded_in"))
    untraced = 0
    ep = os.path.join(bd, "enrichment.jsonl")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    e = json.loads(line)
                    if e.get("kind") == "кросс-домен" and not e.get("traces_to_kernel"):
                        untraced += 1
    ok = groundless == 0 and untraced == 0
    print(f"[доктор-калибровка] {advisor_dir}: безземельных кернелов {groundless}, "
          f"кросс-домен без trace {untraced} → {'✓ OK' if ok else '✗ ГЕЙТ'}")
    return {"ok": ok, "groundless_kernels": groundless, "untraced_cross_domain": untraced}
```
(`json` уже импортирован в doctor.py.)

- [ ] **Step 4: Run, expect PASS** (3 passed) + full suite зелёный.

- [ ] **Step 5: Commit**
```bash
git add scripts/corpusbuild/doctor.py tests/test_corpus_doctor_calib.py
git commit -m "doctor: калибровочные инварианты графа — безземельные кернелы + кросс-домен без trace"
```

---

### Task 10: Эксперимент A — мост даёт recall (research-скрипт)

**Files:**
- Create: `scripts/exp_bridge.py`
- (research-скрипт; юнит-гейта нет, но обязан запускаться end-to-end)

- [ ] **Step 1: Реализовать `scripts/exp_bridge.py`**
```python
#!/usr/bin/env python3
"""Эксперимент A: добавляет ли русский Тарасов-мост recall P1-якорей над translate-query?

Powered-набор (back-translation, не круговой): held-out P1-пассаж → LLM пишет русский ситуац-вопрос,
ответ=пассаж → gold=пассаж. Условия: B0 (наивный RU→P1), B1 (translate-query RU→EN→P1),
T (RU→Тарасов→links→P1), T+B1. Метрика recall@k, значимость McNemar (T+B1 vs B1).
"""
import os, sys, json, urllib.request, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild import embed, ids, paths

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GEN_MODEL = os.getenv("KERNEL_MODEL", "gemma3:27b")
ADV = sys.argv[1] if len(sys.argv) > 1 else "advisors/machiavelli"
N = int(os.getenv("EXP_N", "100"))
SEED = int(os.getenv("EXP_SEED", "7"))


def _gen(prompt, temp=0.4):
    body = json.dumps({"model": GEN_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": temp}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("response", "").strip()


def make_query_ru(passage):
    return _gen(f"Английский пассаж Макиавелли:\n{passage[:700]}\n\nСформулируй ОДИН короткий вопрос "
                f"ПО-РУССКИ о реальной ситуации, ответ на который даёт именно этот пассаж. Только вопрос.")


def translate_to_en(q_ru):
    return _gen(f"Translate to English, output only the translation:\n{q_ru}", temp=0.0)


def recall_at(ranked_ids, gold_id, ks=(1, 5, 10)):
    return {k: int(gold_id in ranked_ids[:k]) for k in ks}


def main():
    random.seed(SEED)
    corpus = ids.load_corpus(ADV)
    p1 = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c["text"]) > 300]
    s1 = [c for c in corpus if c["tier"] in ("S1", "S2")]
    # held-out: фиксируем сид, сэмплируем gold-пассажи
    gold = random.sample(p1, min(N, len(p1)))
    train_p1 = [c for c in p1]  # ретрив-пул = весь P1 (gold внутри — recall честный)
    p1vec = embed.embed_texts([c["text"] for c in train_p1])
    p1ids = [c["id"] for c in train_p1]
    s1vec = embed.embed_texts([c["text"] for c in s1])
    # links: s1_id -> [p1_id…]
    links = {}
    lp = os.path.join(paths.build_dir(ADV), "links.jsonl")
    with open(lp, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                l = json.loads(line); links.setdefault(l["src"], []).append(l["dst"])

    def rank_p1(qvec):
        scored = sorted(zip(p1ids, (embed.cosine(qvec, v) for v in p1vec)), key=lambda t: -t[1])
        return [pid for pid, _ in scored]

    def rank_via_bridge(qvec):
        s1ranked = sorted(zip([c["id"] for c in s1], (embed.cosine(qvec, v) for v in s1vec)),
                          key=lambda t: -t[1])
        out = []
        for sid, _ in s1ranked:
            for pid in links.get(sid, []):
                if pid not in out:
                    out.append(pid)
        return out

    agg = {c: {1: 0, 5: 0, 10: 0} for c in ("B0", "B1", "T", "T+B1")}
    paired = {1: [], 5: [], 10: []}  # для McNemar T+B1 vs B1
    for g in gold:
        q_ru = make_query_ru(g["text"])
        q_en = translate_to_en(q_ru)
        v_ru = embed.embed_texts([q_ru])[0]
        v_en = embed.embed_texts([q_en])[0]
        r_b0 = rank_p1(v_ru)
        r_b1 = rank_p1(v_en)
        r_t = rank_via_bridge(v_ru)
        r_tb1 = r_t + [pid for pid in r_b1 if pid not in r_t]  # union, мост впереди
        for cond, r in (("B0", r_b0), ("B1", r_b1), ("T", r_t), ("T+B1", r_tb1)):
            for k, hit in recall_at(r, g["id"]).items():
                agg[cond][k] += hit
        for k in (1, 5, 10):
            paired[k].append((int(g["id"] in r_b1[:k]), int(g["id"] in r_tb1[:k])))

    n = len(gold)
    print(f"\n=== Exp A: {ADV}, N={n}, сид={SEED} ===")
    for cond in ("B0", "B1", "T", "T+B1"):
        print(f"{cond:5} recall@1={agg[cond][1]/n:.2%}  @5={agg[cond][5]/n:.2%}  @10={agg[cond][10]/n:.2%}")
    # McNemar T+B1 vs B1 на recall@5
    b, c = 0, 0  # b: B1 hit & T+B1 miss; c: B1 miss & T+B1 hit
    for hb1, htb1 in paired[5]:
        b += (hb1 and not htb1); c += (htb1 and not hb1)
    import math
    chi = ((abs(b - c) - 1) ** 2) / (b + c) if (b + c) else 0.0
    sig = "✓ значимо (p<0.05)" if chi > 3.84 else "✗ не значимо"
    print(f"\nMcNemar T+B1 vs B1 @5: discordant b={b} c={c}  χ²={chi:.2f}  {sig}")
    print("ВЫВОД: мост полезен, если T+B1 > B1 и McNemar значим; иначе — театр, энричмент не оправдан.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-прогон малым N (сначала построить links!)**

Run:
```bash
cd ~/personal/Projects/personal-board-skill-2026-06-10
python3 -c "import sys; sys.path.insert(0,'scripts'); from corpusbuild import link; link.build_links('advisors/machiavelli')"
EXP_N=8 python3 scripts/exp_bridge.py advisors/machiavelli
```
Expected: печатает таблицу recall@k для B0/B1/T/T+B1 и строку McNemar без ошибок. (N=8 — только проверка работоспособности, не статистика.)

- [ ] **Step 3: Полный прогон N=100**

Run: `EXP_N=100 python3 scripts/exp_bridge.py advisors/machiavelli | tee /tmp/exp_bridge.log`
Зафиксировать вывод. Интерпретация: headline = T+B1 vs B1 (McNemar). Если T+B1 ≤ B1 — мост не оправдан, доложить юзеру ДО дальнейшего энричмента.

- [ ] **Step 4: Commit (скрипт; логи/данные gitignored)**
```bash
git add scripts/exp_bridge.py
git commit -m "exp: Эксперимент A — мост-recall (back-translation, B0/B1/T/T+B1, McNemar)"
```

---

### Task 11: граф-валидация — рёбра не галлюцинированы

**Files:**
- Create: `scripts/exp_graph.py`

- [ ] **Step 1: Реализовать `scripts/exp_graph.py`**
```python
#!/usr/bin/env python3
"""Граф-валидация (L2.3.3): рёбра 'заземляет' (кернел→P1) не выдуманы — заземляющие пассажи кернела
объясняют ОТЛОЖЕННЫЕ пассажи лучше случайных рёбер. Перестановочный тест.

Метод: для каждого кернела взять его grounded_in (заземление) как «якоря»; held-out = прочие P1.
own = средний max-cos held-out к якорям своего кернела; null = к случайным якорям той же мощности.
Доля own>null vs 50% — биномиальный/перестановочный.
"""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild import embed, ids, paths

ADV = sys.argv[1] if len(sys.argv) > 1 else "advisors/machiavelli"
SEED = int(os.getenv("EXP_SEED", "7"))


def main():
    random.seed(SEED)
    corpus = ids.load_corpus(ADV)
    p1 = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c["text"]) > 250]
    byid = {c["id"]: c for c in p1}
    kp = os.path.join(paths.build_dir(ADV), "kernels.json")
    kernels = json.load(open(kp, encoding="utf-8"))
    vecs = {c["id"]: v for c, v in zip(p1, embed.embed_texts([c["text"] for c in p1]))}
    allids = list(vecs)
    wins = total = 0
    for k in kernels:
        anchors = [a for a in k.get("grounded_in", []) if a in vecs]
        if len(anchors) < 2:
            continue
        held = [i for i in allids if i not in set(anchors)]
        rnd = random.sample(held, len(anchors))
        for hid in held:
            hv = vecs[hid]
            own = max(embed.cosine(hv, vecs[a]) for a in anchors)
            null = max(embed.cosine(hv, vecs[a]) for a in rnd)
            wins += own > null; total += 1
    p = wins / total if total else 0.0
    import math
    z = (p - 0.5) / math.sqrt(0.25 / total) if total else 0.0
    sig = "✓ значимо" if abs(z) > 1.96 else "✗ не значимо"
    print(f"=== граф-валидация {ADV}: own>null {wins}/{total} = {p:.1%}  z={z:+.2f}  {sig} ===")
    print("ВЫВОД: рёбра заземления не галлюцинированы, если own>null значимо выше 50%.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Прогон (нужны kernels.json — сначала build_kernels)**

Run:
```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); from corpusbuild import kernels; kernels.build_kernels('advisors/machiavelli', 'Niccolò Machiavelli')"
python3 scripts/exp_graph.py advisors/machiavelli | tee /tmp/exp_graph.log
```
Expected: печатает own>null долю + z + значимость без ошибок.

- [ ] **Step 3: Commit**
```bash
git add scripts/exp_graph.py
git commit -m "exp: граф-валидация — рёбра заземления не галлюцинированы (перестановочный тест)"
```

---

## Финал (после всех задач)
- Прогнать `python3 -m pytest tests/ -q` — всё зелёное.
- Прогнать `build_enrichment` + `assemble_graph` для Макиавелли, доктор-калибровка `✓ OK`.
- Доложить юзеру результаты Exp A (Task 10) и граф-валидации (Task 11) — это и есть фальсифицируемые исходы.
- Финальное код-ревью всей подсистемы, затем `superpowers:finishing-a-development-branch`.
```
```
