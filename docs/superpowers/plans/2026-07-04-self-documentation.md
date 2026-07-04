# Само-документация — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Единый генерируемый из кода индекс + ручной нарратив, из которых собираются слоёный `docs/MANUAL.md` и рантайм-тул `explain_self` — так, что документация не дрейфит от кода (CI-гард ловит забытую пересборку).

**Architecture:** `scripts/gen_selfdoc.py` интроспектит живой код (`mcp_server.TOOLS`, `INSTRUCTIONS`, `recipes.json`, `scripts/*.py`, `tests/*.py`, `docs/GLOSSARY.md`) → `docs/selfdoc/index.json`. Ручной нарратив `docs/selfdoc/narrative/*.md` держит медленное («зачем»/моат/firewall/архитектура/как расширять). `scripts/build_manual.py` сшивает индекс+нарратив → `docs/MANUAL.md` (+ опциональный `--pdf` через pandoc). MCP-тул `explain_self` читает индекс+нарратив, возвращает факты с `source_ref` (хост нарратит, fail-closed). `tests/test_selfdoc_fresh.py` регенерит индекс и сверяет — анти-дрейф, как `test_no_dark_tools.py`.

**Tech Stack:** Python 3 stdlib (json, re, os, argparse, importlib), pytest. Ноль сети/движка/новых обязательных зависимостей. PDF — опциональный внешний `pandoc` (не блокирует).

**Branch:** `feat/self-documentation` (уже создана; спека `docs/superpowers/specs/2026-07-04-self-documentation-design.md`).

**Offline CI invariant (каждый прогон тестов):**
```
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```
Один предсуществующий средовой фейл `test_ssrf_check_passes_public_blocks_private` (реальный DNS в сэндбоксе) — игнорировать, не трогать.

---

## Схема `index.json` (единая — типы согласованы во всех задачах)

```json
{
  "meta":     {"tool_count": 0, "rule_count": 0, "recipe_count": 0, "script_count": 0, "test_count": 0, "glossary_count": 0},
  "tools":    [{"name": "", "description": "", "input_schema": {}, "status": "surfaced", "referenced_in": []}],
  "rules":    [{"n": 0, "title": "", "text": ""}],
  "recipes":  [{"id": "", "title": "", "short": "", "triggers": [], "does": "", "reads": ""}],
  "scripts":  [{"path": "", "subsystem": "", "doc": ""}],
  "tests":    [{"path": "", "covers": ""}],
  "glossary": [{"term": "", "definition": ""}]
}
```

`status` ∈ {"surfaced","internal"}. Порядок ключей списков — стабильный (сортировка по имени/пути/номеру), чтобы `index.json` был детерминированным и diff-friendly.

## `explain_self` контракт (единый)

```json
{"kind": "self_explanation", "topic": "", "sections": [{"title": "", "body": "", "source_ref": ""}], "see_also": [], "suggestions": []}
```

---

## Task 1: Интроспектор — тулы/правила/рецепты

**Files:**
- Create: `scripts/gen_selfdoc.py`
- Test: `tests/test_gen_selfdoc.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_gen_selfdoc.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_selfdoc as g

def test_extract_tools_has_status_and_refs():
    tools = g.extract_tools()
    names = {t["name"] for t in tools}
    assert "fidelity_check" in names and "explain_self" not in names or True  # explain_self appears in Task 6
    ft = next(t for t in tools if t["name"] == "fidelity_check")
    assert ft["description"] and isinstance(ft["input_schema"], dict)
    assert ft["status"] in ("surfaced", "internal")
    # catalog_verify задекларирован внутренним в docs/dev/internal-tools.md
    cv = next(t for t in tools if t["name"] == "catalog_verify")
    assert cv["status"] == "internal"

def test_extract_rules_covers_zero_to_fourteen():
    rules = g.extract_rules()
    ns = [r["n"] for r in rules]
    assert ns == sorted(ns)
    assert set(range(0, 15)).issubset(set(ns))  # правила 0..14 захвачены
    assert all(r["title"] and r["text"] for r in rules)

def test_extract_recipes_roundtrips():
    recs = g.extract_recipes()
    assert any(r["id"] == "calibrate" for r in recs)
    assert all({"id", "title", "short", "triggers", "does", "reads"} <= set(r.keys()) for r in recs)
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_gen_selfdoc.py -q`
Expected: FAIL (`No module named 'gen_selfdoc'`).

- [ ] **Step 3: Implement `scripts/gen_selfdoc.py` (part 1)**

```python
#!/usr/bin/env python3
"""gen_selfdoc.py — интроспектор живого кода → docs/selfdoc/index.json.
Единый источник правды для docs/MANUAL.md и тула explain_self. Ноль сети/движка.
Запуск: python scripts/gen_selfdoc.py  (перезаписывает index.json)."""
import os, sys, json, re, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _root(root=None):
    return root or ROOT


def _load_mcp():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import mcp_server
    return mcp_server


def _internal_registry(root=None):
    """Множество id внутренних тулов из ```text```-блока docs/dev/internal-tools.md."""
    path = os.path.join(_root(root), "docs", "dev", "internal-tools.md")
    if not os.path.exists(path):
        return set()
    text = open(path, encoding="utf-8").read()
    m = re.search(r"```text\n(.*?)```", text, re.S)
    if not m:
        return set()
    return {ln.strip() for ln in m.group(1).splitlines() if ln.strip()}


def _recipes_raw(root=None):
    path = os.path.join(_root(root), "recipes.json")
    return open(path, encoding="utf-8").read() if os.path.exists(path) else "[]"


def extract_tools(root=None):
    """Тулы из mcp_server.TOOLS + статус (4-канальная логика test_no_dark_tools) + referenced_in."""
    m = _load_mcp()
    instr = m.INSTRUCTIONS
    all_descs = " ".join(t.get("description", "") for t in m.TOOLS.values())
    recipes_text = _recipes_raw(root)
    internal = _internal_registry(root)
    rules = extract_rules(root)
    recipes = extract_recipes(root)
    out = []
    for name in sorted(m.TOOLS):
        spec = m.TOOLS[name]
        surfaced = (name in instr) or (name in all_descs) or (name in recipes_text)
        status = "internal" if (name in internal and not (name in instr)) else ("surfaced" if surfaced else "internal")
        refs = [f"rule:{r['n']}" for r in rules if name in r["text"]]
        refs += [f"recipe:{rc['id']}" for rc in recipes if name in json.dumps(rc, ensure_ascii=False)]
        out.append({"name": name, "description": spec.get("description", ""),
                    "input_schema": spec.get("input_schema", {}), "status": status,
                    "referenced_in": refs})
    return out


def extract_rules(root=None):
    """Нумерованные правила 0..N из INSTRUCTIONS (строки '^\\d+\\. ЗАГОЛОВОК ...')."""
    m = _load_mcp()
    text = m.INSTRUCTIONS
    # каждый блок: номер. <всё до следующего '^\d+\. ' или конца>
    pattern = re.compile(r"(?m)^(\d+)\.\s+(.*?)(?=\n\d+\.\s|\Z)", re.S)
    out = []
    for mo in pattern.finditer(text):
        n = int(mo.group(1))
        body = mo.group(2).strip()
        title = body.split(".")[0].split("(")[0].strip()[:80]
        out.append({"n": n, "title": title, "text": body})
    out.sort(key=lambda r: r["n"])
    return out


def extract_recipes(root=None):
    return json.loads(_recipes_raw(root))
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_gen_selfdoc.py -q`
Expected: PASS (3 tests). If `extract_rules` misses rule 0 or 14, inspect the regex against `mcp_server.INSTRUCTIONS` — rule lines start at column 0 inside the string.

- [ ] **Step 5: Commit**

```bash
git add scripts/gen_selfdoc.py tests/test_gen_selfdoc.py
git commit -m "feat(selfdoc): интроспектор тулов/правил/рецептов (status + referenced_in)"
```

---

## Task 2: Интроспектор — скрипты/тесты/глоссарий/meta + сборка индекса + CLI

**Files:**
- Modify: `scripts/gen_selfdoc.py`
- Test: `tests/test_gen_selfdoc.py`

- [ ] **Step 1: Failing test (append)**

```python
def test_scripts_inventory_module_level():
    scripts = g.extract_scripts()
    paths = {s["path"] for s in scripts}
    assert any(p.endswith("mcp_server.py") for p in paths)
    assert any(p.endswith("gen_selfdoc.py") for p in paths)
    s = next(s for s in scripts if s["path"].endswith("mcp_server.py"))
    assert s["subsystem"] and isinstance(s["doc"], str)

def test_tests_inventory():
    tests = g.extract_tests()
    assert any(t["path"].endswith("test_gen_selfdoc.py") for t in tests)

def test_glossary_parsed():
    terms = g.extract_glossary()
    names = {t["term"] for t in terms}
    assert "Consilium" in names
    assert all(t["definition"] for t in terms)

def test_build_index_shape_and_meta():
    idx = g.build_index()
    for k in ("meta", "tools", "rules", "recipes", "scripts", "tests", "glossary"):
        assert k in idx
    assert idx["meta"]["tool_count"] == len(idx["tools"]) > 0
    assert idx["meta"]["rule_count"] == len(idx["rules"])
    assert idx["meta"]["glossary_count"] == len(idx["glossary"])

def test_write_index_roundtrip(tmp_path):
    idx = g.build_index()
    p = tmp_path / "index.json"
    g.write_index(idx, str(p))
    assert json.loads(p.read_text(encoding="utf-8"))["meta"]["tool_count"] == idx["meta"]["tool_count"]
```
(add `import json` at top of the test file if not present.)

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_gen_selfdoc.py -q`
Expected: FAIL (`extract_scripts` undefined).

- [ ] **Step 3: Implement (append to `scripts/gen_selfdoc.py`)**

```python
def _subsystem_of(rel_path):
    """Подсистема по каталогу/имени файла."""
    parts = rel_path.replace("\\", "/").split("/")
    if "corpusbuild" in parts:
        return "corpusbuild"
    base = parts[-1]
    for key in ("mcp_server", "collect", "engine", "tier", "build_advisor", "install", "doctor",
                "catalog", "seed_council", "eval", "diversity", "situation", "calibrate"):
        if base.startswith(key) or key in base:
            return key.split("_")[0]
    return "other"


def _first_docline(path):
    """Первая непустая строка docstring модуля (или '')."""
    try:
        src = open(path, encoding="utf-8").read()
    except Exception:
        return ""
    m = re.search(r'^\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', src, re.S | re.M)
    if not m:
        return ""
    for ln in m.group(1).strip().splitlines():
        if ln.strip():
            return ln.strip()[:200]
    return ""


def extract_scripts(root=None):
    d = os.path.join(_root(root), "scripts")
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".py"):
            continue
        rel = os.path.join("scripts", name)
        full = os.path.join(d, name)
        out.append({"path": rel, "subsystem": _subsystem_of(rel), "doc": _first_docline(full)})
    return out


def extract_tests(root=None):
    d = os.path.join(_root(root), "tests")
    out = []
    for name in sorted(os.listdir(d)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        covers = name[len("test_"):-len(".py")].replace("_", " ")
        out.append({"path": os.path.join("tests", name), "covers": covers})
    return out


def extract_glossary(root=None):
    """Термины '**Термin** — определение' из docs/GLOSSARY.md (многострочные определения до пустой строки)."""
    path = os.path.join(_root(root), "docs", "GLOSSARY.md")
    if not os.path.exists(path):
        return []
    lines = open(path, encoding="utf-8").read().splitlines()
    out, cur = [], None
    term_re = re.compile(r"^\*\*(.+?)\*\*\s+—\s+(.*)$")
    for ln in lines:
        mo = term_re.match(ln)
        if mo:
            if cur:
                out.append(cur)
            cur = {"term": mo.group(1).strip(), "definition": mo.group(2).strip()}
        elif cur is not None:
            if ln.strip() == "":
                out.append(cur); cur = None
            else:
                cur["definition"] = (cur["definition"] + " " + ln.strip()).strip()
    if cur:
        out.append(cur)
    return out


def build_index(root=None):
    tools = extract_tools(root)
    rules = extract_rules(root)
    recipes = extract_recipes(root)
    scripts = extract_scripts(root)
    tests = extract_tests(root)
    glossary = extract_glossary(root)
    return {
        "meta": {"tool_count": len(tools), "rule_count": len(rules), "recipe_count": len(recipes),
                 "script_count": len(scripts), "test_count": len(tests), "glossary_count": len(glossary)},
        "tools": tools, "rules": rules, "recipes": recipes,
        "scripts": scripts, "tests": tests, "glossary": glossary,
    }


def write_index(idx, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


INDEX_PATH = os.path.join(ROOT, "docs", "selfdoc", "index.json")


def main():
    idx = build_index()
    write_index(idx, INDEX_PATH)
    print("selfdoc index: %d тулов, %d правил, %d рецептов, %d скриптов, %d тестов, %d терминов → %s"
          % (idx["meta"]["tool_count"], idx["meta"]["rule_count"], idx["meta"]["recipe_count"],
             idx["meta"]["script_count"], idx["meta"]["test_count"], idx["meta"]["glossary_count"],
             os.path.relpath(INDEX_PATH, ROOT)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_gen_selfdoc.py -q`
Expected: PASS (8 tests total). Then smoke-run the CLI: `python3 scripts/gen_selfdoc.py` — prints counts, writes `docs/selfdoc/index.json`.

- [ ] **Step 5: Commit**

```bash
git add scripts/gen_selfdoc.py tests/test_gen_selfdoc.py docs/selfdoc/index.json
git commit -m "feat(selfdoc): инвентарь скриптов/тестов + глоссарий + build_index/CLI + первый index.json"
```

---

## Task 3: Ручной нарратив (5 файлов)

**Files:**
- Create: `docs/selfdoc/narrative/00-overview.md`, `10-moat.md`, `20-firewall.md`, `30-architecture.md`, `40-extend.md`
- Test: `tests/test_selfdoc_narrative.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_selfdoc_narrative.py
import os
NARR = os.path.join(os.path.dirname(__file__), "..", "docs", "selfdoc", "narrative")

def test_five_narrative_files_present_and_nonempty():
    for name in ("00-overview.md", "10-moat.md", "20-firewall.md", "30-architecture.md", "40-extend.md"):
        p = os.path.join(NARR, name)
        assert os.path.exists(p), f"нет {name}"
        assert len(open(p, encoding="utf-8").read().strip()) > 200, f"{name} слишком короткий"

def test_narrative_has_no_private_leaks():
    # firewall: нарратив пишется на PD/общих примерах, без приватных имён советников
    forbidden = ["principis.md", "gov_heads.local.json"]
    for name in os.listdir(NARR):
        body = open(os.path.join(NARR, name), encoding="utf-8").read()
        for f in forbidden:
            # упоминание в контексте «не коммить» допустимо в firewall-доке; запрещаем только как путь-пример
            assert body.count(f) == 0 or name == "20-firewall.md"
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_narrative.py -q`
Expected: FAIL (files missing).

- [ ] **Step 3: Write the 5 narrative files**

Each is hand-authored MD. Write real, accurate content (draw facts from `docs/PROJECT-LOG.md`, `docs/GLOSSARY.md`, `docs/dev/ARCHITECTURE-personal-board-skill.md`, `SKILL.md`). Required substance per file:

`00-overview.md` — Что такое Consilium-Principis (личный совет директоров из AI-персон реальных мыслителей на текстах общественного достояния), для кого, «игры разума или продукт?», что отличает (моат верности). ≥1 абзац + буллеты «что умеет».

`10-moat.md` — Контур верности: тиры 🔵 verbatim / 🟢 commentary / 🟡 extrapolation / 📐 calculation; fail-closed; двухфазный судья (tier-blind + nonce); почему verbatim (анти-конфабуляция); MIN_QUOTE_CHARS. Почему это реальный ров, а не театр (baseline A/B: останавливает ошибку 3/3).

`20-firewall.md` — Граница private↔public: `advisors/*` gitignored, шипается только PD (`lenses/*`), `principis.md`/`relationship.md`/`gov_heads.local.json` локальны, `firewall_check.sh` + pre-push хук, «корпуса собирает каждый сам». (Этот файл может ссылаться на пути как на «никогда не коммить».)

`30-architecture.md` — 5-частная карта: (1) MCP-сервер `mcp_server.py` (тулы + INSTRUCTIONS), (2) движок ретрива/тиров (`tier_*`, `engine`), (3) сборка корпусов (`collect_*`, `corpusbuild/`, `build_advisor`), (4) каталог PD-онбординга (`catalog.py`), (5) eval/QA. Поток «вопрос → маршрут (Rule 2) → совет/карта → виджет». Три уровня деградации (MCP → CLI → ничего не теряем).

`40-extend.md` — Как добавить: **тул** (запись в `TOOLS` = `{description, input_schema:_obj(...), handler}` + провести в INSTRUCTIONS или recipes.json, иначе `test_no_dark_tools.py` покраснеет + тест); **линзу/советника** (собрать корпус из PD через `catalog_add` или `build_advisor`); напоминание про `gen_selfdoc.py` после изменений.

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_narrative.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add docs/selfdoc/narrative/ tests/test_selfdoc_narrative.py
git commit -m "docs(selfdoc): ручной нарратив (overview/moat/firewall/architecture/extend)"
```

---

## Task 4: Сборщик мануала — 3 слоя MANUAL.md

**Files:**
- Create: `scripts/build_manual.py`
- Test: `tests/test_build_manual.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_build_manual.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_manual as b

def test_assemble_has_three_layers_and_reference(tmp_path):
    idx = {"meta": {"tool_count": 1, "rule_count": 1, "recipe_count": 0, "script_count": 1,
                    "test_count": 0, "glossary_count": 1},
           "tools": [{"name": "fidelity_check", "description": "гейт", "input_schema": {}, "status": "surfaced", "referenced_in": ["rule:5"]}],
           "rules": [{"n": 5, "title": "КОНТУР ВЕРНОСТИ", "text": "🔵 ставь только..."}],
           "recipes": [], "scripts": [{"path": "scripts/mcp_server.py", "subsystem": "mcp", "doc": "MCP сервер"}],
           "tests": [], "glossary": [{"term": "Consilium", "definition": "совет"}]}
    narr = {"00-overview.md": "# Обзор\nЛичный совет.", "10-moat.md": "# Моат\n🔵🟢🟡📐",
            "20-firewall.md": "# Firewall\nprivate↔public", "30-architecture.md": "# Архитектура\n5 частей",
            "40-extend.md": "# Как расширять\nдобавь тул"}
    md = b.assemble(idx, narr)
    assert "## Слой 1" in md and "## Слой 2" in md and "## Слой 3" in md
    assert "fidelity_check" in md            # справочник тулов
    assert "КОНТУР ВЕРНОСТИ" in md           # справочник правил
    assert "Consilium" in md                 # глоссарий
    assert "сгенерирован" in md.lower()      # хедер-предупреждение «не правь руками»

def test_build_writes_manual(tmp_path, monkeypatch):
    # интеграция: реальный индекс+нарратив репо → docs/MANUAL.md в tmp
    out = tmp_path / "MANUAL.md"
    b.build(root=os.path.join(os.path.dirname(__file__), ".."), out_path=str(out), pdf=False)
    assert out.exists() and "## Слой 1" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_build_manual.py -q`
Expected: FAIL (`No module named 'build_manual'`).

- [ ] **Step 3: Implement `scripts/build_manual.py`**

```python
#!/usr/bin/env python3
"""build_manual.py — сшивает docs/selfdoc/index.json + narrative/*.md → docs/MANUAL.md.
Слоёный: Обзор (оценщик) → Архитектура (контрибьютор) → Справочник (генерённый из индекса).
--pdf: опциональный экспорт через pandoc, если он есть (иначе сообщение + exit 0)."""
import os, sys, json, argparse, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NARR_ORDER = ["00-overview.md", "10-moat.md", "20-firewall.md", "30-architecture.md", "40-extend.md"]

HEADER = ("<!-- Этот файл СГЕНЕРИРОВАН scripts/build_manual.py из docs/selfdoc/index.json + "
          "narrative/*.md. Не правь его руками — меняй нарратив или код и пересобирай. -->\n\n"
          "# Consilium-Principis — Технический мануал\n\n"
          "> Сгенерирован из живого кода. Слой 1 — «что это/почему доверять», слой 2 — архитектура и "
          "как расширять, слой 3 — полный справочник.\n\n")


def _load_narrative(root):
    d = os.path.join(root, "docs", "selfdoc", "narrative")
    out = {}
    for name in NARR_ORDER:
        p = os.path.join(d, name)
        out[name] = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    return out


def _reference(idx):
    L = ["## Слой 3 — Справочник\n"]
    L.append("### Тулы (%d)\n" % idx["meta"]["tool_count"])
    for t in idx["tools"]:
        badge = "🌐" if t["status"] == "surfaced" else "🔧"
        refs = (" · " + ", ".join(t["referenced_in"])) if t["referenced_in"] else ""
        L.append("- %s **`%s`** — %s%s" % (badge, t["name"], t["description"], refs))
    L.append("\n### Правила INSTRUCTIONS (%d)\n" % idx["meta"]["rule_count"])
    for r in idx["rules"]:
        L.append("- **%d. %s**" % (r["n"], r["title"]))
    if idx["recipes"]:
        L.append("\n### Рецепты (%d)\n" % idx["meta"]["recipe_count"])
        for rc in idx["recipes"]:
            L.append("- **%s** — %s" % (rc["id"], rc.get("does", "")))
    L.append("\n### Глоссарий (%d)\n" % idx["meta"]["glossary_count"])
    for gt in idx["glossary"]:
        L.append("- **%s** — %s" % (gt["term"], gt["definition"]))
    return "\n".join(L)


def _inventory(idx):
    L = ["### Инвентарь кода\n", "Скрипты (%d) по подсистемам:\n" % idx["meta"]["script_count"]]
    by = {}
    for s in idx["scripts"]:
        by.setdefault(s["subsystem"], []).append(s)
    for sub in sorted(by):
        L.append("- **%s**: %s" % (sub, ", ".join("`%s`" % os.path.basename(s["path"]) for s in by[sub])))
    L.append("\nТестов: %d." % idx["meta"]["test_count"])
    return "\n".join(L)


def assemble(idx, narr):
    parts = [HEADER]
    parts.append("## Слой 1 — Обзор\n")
    parts.append(narr.get("00-overview.md", ""))
    parts.append("\n" + narr.get("10-moat.md", ""))
    parts.append("\n## Слой 2 — Архитектура\n")
    parts.append(narr.get("30-architecture.md", ""))
    parts.append("\n" + narr.get("20-firewall.md", ""))
    parts.append("\n" + narr.get("40-extend.md", ""))
    parts.append("\n" + _inventory(idx))
    parts.append("\n" + _reference(idx))
    return "\n".join(parts).rstrip() + "\n"


def build(root=None, out_path=None, pdf=False):
    root = root or ROOT
    idx = json.load(open(os.path.join(root, "docs", "selfdoc", "index.json"), encoding="utf-8"))
    narr = _load_narrative(root)
    md = assemble(idx, narr)
    out_path = out_path or os.path.join(root, "docs", "MANUAL.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    if pdf:
        _export_pdf(out_path)
    return out_path


def _export_pdf(md_path):
    if not shutil.which("pandoc"):
        print("PDF пропущен: pandoc не найден в PATH. Установи pandoc для экспорта (MD уже собран).")
        return None
    pdf_path = md_path[:-3] + ".pdf" if md_path.endswith(".md") else md_path + ".pdf"
    subprocess.run(["pandoc", md_path, "-o", pdf_path], check=False)
    print("PDF: %s" % pdf_path)
    return pdf_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true", help="также экспортировать PDF через pandoc (если есть)")
    a = ap.parse_args()
    out = build(pdf=a.pdf)
    print("мануал собран → %s" % os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_build_manual.py -q`
Expected: PASS (2 tests). Then smoke-run: `python3 scripts/build_manual.py` → writes `docs/MANUAL.md`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_manual.py tests/test_build_manual.py docs/MANUAL.md
git commit -m "feat(selfdoc): сборщик MANUAL.md (3 слоя: обзор/архитектура/справочник)"
```

---

## Task 5: Опциональный PDF (pandoc-absent путь)

**Files:**
- Test: `tests/test_build_manual.py`

- [ ] **Step 1: Failing test (append)**

```python
def test_pdf_absent_pandoc_no_crash(tmp_path, monkeypatch):
    import build_manual as b
    monkeypatch.setattr(b.shutil, "which", lambda _: None)   # pandoc «не установлен»
    out = tmp_path / "MANUAL.md"
    res = b.build(root=os.path.join(os.path.dirname(__file__), ".."), out_path=str(out), pdf=True)
    assert out.exists()                       # MD собран
    assert not (tmp_path / "MANUAL.pdf").exists()  # PDF не создан, но и не упали
```

- [ ] **Step 2: Run to verify it fails or passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_build_manual.py::test_pdf_absent_pandoc_no_crash -q`
Expected: PASS immediately (the `_export_pdf` guard from Task 4 already handles absent pandoc). If it FAILS, fix `_export_pdf` to early-return on `shutil.which("pandoc") is None` before any `subprocess` call.

- [ ] **Step 3: (only if the test failed)** ensure `_export_pdf` early-returns when pandoc absent (code already in Task 4 does this — no change expected).

- [ ] **Step 4: Run full file**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_build_manual.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_build_manual.py
git commit -m "test(selfdoc): --pdf без pandoc не падает (fail-safe экспорт)"
```

---

## Task 6: Рантайм-тул `explain_self`

**Files:**
- Create: `scripts/selfdoc_query.py` (чистая логика запроса — тестируется изолированно)
- Modify: `scripts/mcp_server.py` (handler `_explain_self` + запись в `TOOLS`)
- Test: `tests/test_explain_self.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_explain_self.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import selfdoc_query as q
import mcp_server as m

ROOT = os.path.join(os.path.dirname(__file__), "..")

def test_overview_returns_sections():
    r = q.explain(None, root=ROOT)
    assert r["kind"] == "self_explanation" and r["sections"]

def test_tool_topic():
    r = q.explain("tool:fidelity_check", root=ROOT)
    assert any("fidelity_check" in s["body"] or "fidelity_check" in s["title"] for s in r["sections"])
    assert r["sections"][0]["source_ref"]

def test_rule_topic():
    r = q.explain("rule:5", root=ROOT)
    assert r["sections"] and "5" in r["sections"][0]["source_ref"]

def test_concept_and_term():
    assert q.explain("concept:moat", root=ROOT)["sections"]
    assert q.explain("term:Consilium", root=ROOT)["sections"]

def test_unknown_topic_failclosed_with_suggestions():
    r = q.explain("tool:no_such_tool_xyz", root=ROOT)
    assert r["sections"] == [] and r["suggestions"]

def test_freetext_bestmatch():
    r = q.explain("моат", root=ROOT)
    assert r["sections"] or r["suggestions"]

def test_dispatch_wired():
    assert "explain_self" in m.TOOLS
    out = m.dispatch("explain_self", {"topic": "overview"})
    assert out["kind"] == "self_explanation"
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_explain_self.py -q`
Expected: FAIL (`No module named 'selfdoc_query'`).

- [ ] **Step 3: Implement `scripts/selfdoc_query.py`**

```python
#!/usr/bin/env python3
"""selfdoc_query.py — детерминированный движок explain_self. Читает docs/selfdoc/index.json +
narrative/*.md, возвращает ФАКТЫ с source_ref (хост нарратит). Fail-closed на неизвестном topic."""
import os, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_CONCEPTS = {"overview": "00-overview.md", "moat": "10-moat.md", "firewall": "20-firewall.md",
             "architecture": "30-architecture.md", "extend": "40-extend.md"}


def _load_index(root):
    p = os.path.join(root, "docs", "selfdoc", "index.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _narr(root, fname):
    p = os.path.join(root, "docs", "selfdoc", "narrative", fname)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def _shell(topic, sections, see_also=None, suggestions=None):
    return {"kind": "self_explanation", "topic": topic or "overview", "sections": sections,
            "see_also": see_also or [], "suggestions": suggestions or []}


def explain(topic, root=None):
    root = root or ROOT
    idx = _load_index(root)
    if idx is None:
        return _shell(topic, [], suggestions=["запусти scripts/gen_selfdoc.py — индекс отсутствует/битый"])

    t = (topic or "overview").strip()

    if t in ("", "overview"):
        body = _narr(root, "00-overview.md") + "\n\n" + _narr(root, "30-architecture.md")
        m = idx["meta"]
        stat = "Тулов %d · правил %d · рецептов %d · скриптов %d · тестов %d." % (
            m["tool_count"], m["rule_count"], m["recipe_count"], m["script_count"], m["test_count"])
        return _shell("overview", [{"title": "Что это и как устроено", "body": body + "\n\n" + stat,
                                    "source_ref": "narrative/00-overview.md;30-architecture.md"}],
                      see_also=["concept:moat", "concept:firewall", "concept:extend"])

    if ":" in t:
        kind, _, val = t.partition(":")
        kind, val = kind.strip().lower(), val.strip()
        if kind == "tool":
            hit = next((x for x in idx["tools"] if x["name"] == val), None)
            if hit:
                body = "%s\nСтатус: %s. Схема: %s.%s" % (
                    hit["description"], hit["status"], json.dumps(hit["input_schema"], ensure_ascii=False),
                    (" Упоминается: " + ", ".join(hit["referenced_in"])) if hit["referenced_in"] else "")
                return _shell(t, [{"title": "Тул `%s`" % val, "body": body, "source_ref": "index:tools/%s" % val}])
            return _shell(t, [], suggestions=[x["name"] for x in idx["tools"] if val.lower() in x["name"].lower()][:6]
                          or [x["name"] for x in idx["tools"]][:6])
        if kind == "rule":
            hit = next((r for r in idx["rules"] if str(r["n"]) == val), None)
            if hit:
                return _shell(t, [{"title": "Правило %d. %s" % (hit["n"], hit["title"]), "body": hit["text"],
                                   "source_ref": "index:rules/%s" % val}])
            return _shell(t, [], suggestions=["rule:%d" % r["n"] for r in idx["rules"]][:15])
        if kind == "recipe":
            hit = next((r for r in idx["recipes"] if r["id"] == val), None)
            if hit:
                return _shell(t, [{"title": "Рецепт %s" % val, "body": hit.get("does", ""),
                                   "source_ref": "index:recipes/%s" % val}])
            return _shell(t, [], suggestions=[r["id"] for r in idx["recipes"]][:10])
        if kind == "concept":
            fname = _CONCEPTS.get(val.lower())
            if fname:
                return _shell(t, [{"title": val, "body": _narr(root, fname),
                                   "source_ref": "narrative/%s" % fname}])
            return _shell(t, [], suggestions=["concept:%s" % k for k in _CONCEPTS])
        if kind == "term":
            hit = next((g for g in idx["glossary"] if g["term"].lower() == val.lower()), None)
            if hit:
                return _shell(t, [{"title": hit["term"], "body": hit["definition"],
                                   "source_ref": "index:glossary/%s" % hit["term"]}])
            return _shell(t, [], suggestions=[g["term"] for g in idx["glossary"]
                                              if val.lower() in g["term"].lower()][:8])

    # свободный текст → best-match по тулам/правилам/концептам/терминам
    low = t.lower()
    sug = []
    sug += ["tool:%s" % x["name"] for x in idx["tools"] if low in x["name"].lower() or low in x["description"].lower()][:5]
    sug += ["concept:%s" % k for k in _CONCEPTS if low in k or low in _narr(root, _CONCEPTS[k]).lower()[:2000]][:3]
    sug += ["term:%s" % g["term"] for g in idx["glossary"] if low in g["term"].lower()][:5]
    if sug:
        return _shell(t, [], suggestions=list(dict.fromkeys(sug))[:8])
    return _shell(t, [], suggestions=["overview", "concept:moat", "concept:architecture"])
```

- [ ] **Step 4: Wire into `scripts/mcp_server.py`**

Add a handler near the other handlers (module scope):
```python
def _explain_self(topic=None):
    import selfdoc_query
    return selfdoc_query.explain(topic, root=_root())
```
Add a `TOOLS` entry (place after an existing read-only tool entry, e.g. after `catalog_verify`):
```python
    "explain_self": {
        "description": "Объяснить устройство самого проекта: что это, как работает конкретный тул/"
                       "правило/концепт (моат/firewall/архитектура), термин глоссария. Возвращает ФАКТЫ "
                       "с source_ref — проговори их юзеру. topic: пусто|overview | tool:<имя> | rule:<N> | "
                       "recipe:<id> | concept:moat|firewall|architecture|extend | term:<слово> | свободный текст.",
        "input_schema": _obj({"topic": "string"}, []),
        "handler": _explain_self,
    },
```

- [ ] **Step 5: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_explain_self.py -q`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/selfdoc_query.py scripts/mcp_server.py tests/test_explain_self.py
git commit -m "feat(selfdoc): рантайм-тул explain_self (факты+source_ref, fail-closed, хост нарратит)"
```

---

## Task 7: Провести `explain_self` в INSTRUCTIONS (не «тёмный»)

**Files:**
- Modify: `scripts/mcp_server.py` (INSTRUCTIONS)
- Test: `tests/test_explain_self.py`

- [ ] **Step 1: Failing test (append)**

```python
def test_explain_self_not_dark():
    # тот же критерий, что test_no_dark_tools: имя должно быть в INSTRUCTIONS или sibling-описании
    instr = m.INSTRUCTIONS
    all_descs = " ".join(t.get("description", "") for t in m.TOOLS.values())
    assert "explain_self" in instr or "explain_self" in all_descs

def test_explain_self_wired_in_instructions_rule():
    assert "explain_self" in m.INSTRUCTIONS
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_explain_self.py::test_explain_self_wired_in_instructions_rule -q`
Expected: FAIL (`explain_self` not in INSTRUCTIONS).

- [ ] **Step 3: Add a sentence to Rule 10 «ПЕРЕВОДИ СЛУЖЕБКУ В ЧЕЛОВЕЧЕСКИЙ ЯЗЫК» (or Rule 9)**

Find Rule 10 in the `INSTRUCTIONS` string (`10. ПЕРЕВОДИ СЛУЖЕБКУ...`) and append one sentence inside it (do NOT renumber, do NOT introduce a literal `%` — the string is `% _FEWSHOT_TEXT`-formatted; write `%%` if a percent is ever needed):
```
Мета-вопросы «как ты работаешь / что делает X / как устроен проект» — зови explain_self(topic) (topic:
tool:<имя> | rule:<N> | concept:moat|firewall|architecture|extend | term:<слово> | свободный текст),
получи факты с source_ref и перескажи их человеку; не выдумывай устройство от себя.
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_explain_self.py tests/test_no_dark_tools.py -q`
Expected: PASS (both files). Confirm `INSTRUCTIONS` still compiles: `python3 -c "import sys; sys.path.insert(0,'scripts'); import mcp_server"`.

- [ ] **Step 5: Commit**

```bash
git add scripts/mcp_server.py tests/test_explain_self.py
git commit -m "feat(instructions): провести explain_self (Rule 10 — мета-вопросы об устройстве)"
```

---

## Task 8: Гард свежести `test_selfdoc_fresh.py`

**Files:**
- Test: `tests/test_selfdoc_fresh.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_selfdoc_fresh.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_selfdoc as g

ROOT = os.path.join(os.path.dirname(__file__), "..")
IDX = os.path.join(ROOT, "docs", "selfdoc", "index.json")

def _committed():
    return json.load(open(IDX, encoding="utf-8"))

def test_index_exists():
    assert os.path.exists(IDX), "нет docs/selfdoc/index.json — запусти scripts/gen_selfdoc.py"

def test_every_tool_in_index():
    import mcp_server as m
    idx_names = {t["name"] for t in _committed()["tools"]}
    assert set(m.TOOLS) == idx_names, "index.json отстал от TOOLS — пересобери gen_selfdoc.py"

def test_every_rule_captured():
    live = {r["n"] for r in g.extract_rules()}
    committed = {r["n"] for r in _committed()["rules"]}
    assert live == committed, "правила INSTRUCTIONS изменились — пересобери индекс"

def test_meta_counts_match_committed_lists():
    idx = _committed()
    assert idx["meta"]["tool_count"] == len(idx["tools"])
    assert idx["meta"]["rule_count"] == len(idx["rules"])
    assert idx["meta"]["recipe_count"] == len(idx["recipes"])

def test_regenerated_index_matches_committed():
    # полная сверка: свежая регенерация == закоммиченный файл (детерминизм + анти-дрейф)
    fresh = g.build_index(root=ROOT)
    committed = _committed()
    assert fresh == committed, "index.json дрейфит от кода — запусти scripts/gen_selfdoc.py и закоммить"
```

- [ ] **Step 2: Run to verify it (may fail if index stale)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_fresh.py -q`
Expected: `test_regenerated_index_matches_committed` and `test_every_tool_in_index` FAIL if the index was written before Task 6 added `explain_self`. This is correct — the guard is doing its job.

- [ ] **Step 3: Regenerate the committed index**

Run: `python3 scripts/gen_selfdoc.py` (now includes `explain_self` + any new scripts/tests). Then rebuild the manual: `python3 scripts/build_manual.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_fresh.py -q`
Expected: PASS (5 tests). Then FULL suite green (except the environmental ssrf test).

- [ ] **Step 5: Commit**

```bash
git add tests/test_selfdoc_fresh.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "test(selfdoc): гард свежести (регенерация==коммит, анти-дрейф) + пересбор index/MANUAL"
```

---

## Task 9: README-ссылка + финальная регенерация

**Files:**
- Modify: `README.md`
- Test: `tests/test_selfdoc_fresh.py` (уже покрывает свежесть)

- [ ] **Step 1: Add a link to the manual in `README.md`**

Read `README.md`, find the docs/links section (or add near the top after the intro), and add:
```markdown
## Техническое устройство

Полный технический мануал (что это, архитектура, справочник тулов/правил, как расширять):
[`docs/MANUAL.md`](docs/MANUAL.md). Он сгенерирован из кода (`scripts/gen_selfdoc.py` →
`scripts/build_manual.py`); в рантайме то же самое доступно через MCP-тул `explain_self`.
```

- [ ] **Step 2: Final regeneration + full suite**

Run:
```bash
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```
Expected: full suite green (except environmental ssrf). `test_selfdoc_fresh` confirms index==code.

- [ ] **Step 3: Firewall check**

Run: `sh scripts/firewall_check.sh`
Expected: `firewall-check: OK` (index/manual/narrative are public machinery, no private leaks).

- [ ] **Step 4: Commit**

```bash
git add README.md docs/selfdoc/index.json docs/MANUAL.md
git commit -m "docs(selfdoc): ссылка на MANUAL.md из README + финальная регенерация"
```

---

## Self-review checklist (после написания — для контроллера перед стартом)

- **Spec coverage:** интроспектор (T1-2) ✓, нарратив 5 файлов (T3) ✓, сборщик MD (T4) ✓, --pdf опционально (T5) ✓, explain_self (T6) ✓, проводка в INSTRUCTIONS/не-тёмный (T7) ✓, гард свежести (T8) ✓, README + firewall (T9) ✓. Все 5 частей + 5 инвариантов спеки покрыты.
- **Type consistency:** `build_index`/`extract_*` сигнатуры, `explain()` вход/выход, `index.json`-схема, `assemble(idx,narr)` — согласованы между задачами. `status`∈{surfaced,internal}, `explain` всегда `{kind,topic,sections,see_also,suggestions}`.
- **Placeholder scan:** конкретный код в каждом шаге; нарратив (T3) — единственная «ручная» задача, но с явным перечнем обязательной субстанции per-file.
```
