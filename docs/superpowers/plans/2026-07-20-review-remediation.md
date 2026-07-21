# Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the fact-verified findings of the 2026-07-20 six-reviewer full-project review (2 critical + 7 high + 11 medium clusters + low backlog), in priority order, without breaking the offline invariant (1709 passed / 1 skipped) or the fidelity moat.

**Architecture:** Six phases by risk/value: (1) C2 negation-guard — the only confirmed path to a false 🔵; (2) C1+H5+H6 surface unity — moat directives into INSTRUCTIONS, `diversity_check` tool, doc counters + narrative guard; (3) H1+M1/M2/M3 security hardening (file isolation, DoS caps, config whitelist); (4) H7+M4/M9 gate coherence + onboarding (one design gate); (5) H2/H3/H4+M11 structural slices (design-gated); (6) medium/low verify-first backlog. Every code fix is TDD. Every commit is owner-gated — the executor STOPS and asks before each commit; NEVER `git add -A`; NEVER push/merge without explicit owner go.

**Tech Stack:** Python 3 stdlib core (numpy only for semantic tier), pytest, ollama/bge-m3 (gated), mcpb packaging.

**Invariants the executor must hold:**
- Offline invariant after every phase: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` → must stay green (currently 1709 passed / 1 skipped).
- env-touching tests use `monkeypatch`; never leave vars in `os.environ`.
- private advisor slugs NEVER in code/tests/docs/bundle — tests use synthetic corpora under `tmp_path`.
- Tools/rules/tests counts live in `docs/selfdoc/index.json` + generated `docs/MANUAL.md`: after adding/removing any tool, rule, script or test file run `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py` and commit the regenerated files, else `tests/test_selfdoc_fresh.py` fails.
- MCP handlers are pure functions called via `TOOLS[name]["handler"](**args)` (`scripts/mcp_server.py:2425-2427`); tests call `mcp_server.dispatch(name, args)` and patch `mcp_server._root` to `tmp_path` for filesystem fixtures.
- commit ONLY on explicit owner "go", explicit paths only.

**Source findings (reviewer-verified, with reproductions):**
- C1: INSTRUCTIONS (rules 0-17, `scripts/mcp_server.py:2463-2738`) lacks SKILL.md's moat directives — dissent/anti-sycophancy (`SKILL.md:107-115`), frame-check (`SKILL.md:345-355`), diversity-gate (`SKILL.md:325-328`), never_quote (`SKILL.md:121-122`). Plugin-via-MCP is the README-recommended install path, and MCP hosts see ONLY tools + INSTRUCTIONS.
- C2: `_crop_severs_negation` (`scripts/engine/fidelity.py:22-33`) looks at exactly ONE preceding token and `_NEG` lacks `t` (contractions), `without`, `nor`, `cannot`, `никогда`, `никто`, `без`. Confirmed live: «win by cheating» from «you **can't** win by cheating» → 🔵; «believe in omens» from «did **not** in any real sense believe in omens» → 🔵; «cruelty when the state» after «**without**» → 🔵.
- H1: `_do_ingest` (`mcp_server.py:1699-1707`) + `ingest_telegram.write_corpus` (`scripts/ingest_telegram.py:43-48`): write-clamp = whole repo root, silent overwrite — `out_path=".env"` destroys secrets, `out_path="scripts/mcp_server.py"` → RCE at restart.
- H2: `mcp_server.py` god-module (2851 lines, ~117 functions, 7 domains).
- H3: `sys.path.insert` — 76 sites, 4 styles, 5 inside single functions (`scripts/governance.py:114,140,294,319,365`).
- H4: `board.py:94-152` CLI duplicates `_do_build/_do_seed/_do_ingest/_doctor/_setup_full` (`mcp_server.py:1685-1733`).
- H5: `diversity_check.py` is CLI-only; SKILL.md Step 0б declares it mandatory; unreachable from pure MCP hosts.
- H6: doc drift with a blind guard: `SKILL.md:470` «37 шт.» vs 60 tools; `docs/selfdoc/narrative/30-architecture.md:4` «правила 0–14» vs 0–17 (→ `docs/MANUAL.md`); `SKILL.md:36` vs `SKILL.md:287` hybrid contradiction; broken links `SKILL.md:26`, `SKILL.md:290`.
- H7: onboarding leads to a 🟡-only corpus: `scripts/collect_common.py:269` and MANUAL recommend legacy `build_advisor.py` (no tier fields); `build_orchestrator.py:33` note «нет манифеста → всё P1» is false (real: «A» → 🟡); doctor's tiering check skips corpora without build.lock.

---

## File Structure

- `scripts/engine/fidelity.py` — sentence-scoped negation guard (C2).
- `tests/test_fidelity_negation_crop.py` — C2 regression tests (append; reuse its fixture helper if present).
- `scripts/mcp_server.py` — Rule 18 in INSTRUCTIONS (C1); `diversity_check` tool (H5); ingest clamp (H1); `_SENSITIVE` denylist + `_load_source_text` delegation (M1); cite caps (M2); `config_set` whitelist (M3); federation caps (M2).
- `scripts/diversity_check.py` — extract pure `check(paths) -> dict`; `main()` prints from it (H5).
- `tests/test_diversity_check_tool.py` (new) — tool contract tests.
- `scripts/mc_run.py` — `N_MAX` scenario cap (M2).
- `tests/test_mc_run.py` (or nearest MC test file) — cap test.
- `scripts/safe_expr.py` — OverflowError → SafeExprEvalError (M5).
- `scripts/collect_common.py`, `scripts/build_orchestrator.py`, `docs/selfdoc/narrative/*.md`, `scripts/doctor.py` — onboarding path honesty (H7).
- `scripts/relevance_gate.py`, `scripts/engine/__init__.py`, eval entrypoints — `EVAL_ENGINE` scoping (M9).
- `scripts/relevance_judge.py` — judge timeout + circuit breaker (M9).
- `SKILL.md`, `docs/selfdoc/narrative/30-architecture.md`, `CHANGELOG.md`, `QUICKSTART.md`, `install-skill/SKILL.md` — doc honesty (H6, M10).
- `tests/test_selfdoc_fresh.py` — narrative counter guard (H6).

---

## PHASE 1 — C2: negation-guard hardening (the only confirmed false-🔵 path)

### Task 1.1: Sentence-scoped negation guard in `engine/fidelity.py`

**Files:**
- Modify: `scripts/engine/fidelity.py:21-33` (`_NEG`, `_crop_severs_negation`) and `:104` (call site)
- Test: `tests/test_fidelity_negation_crop.py` (append)

**Design (owner-visible tradeoff, pre-approved by this plan):** `_norm` erases punctuation, so a token-window guard both misses distant negation («not in any real sense …») and would false-reject quotes whose preceding *sentence* contains «not». Fix scope = the **sentence**: split the RAW chunk text on sentence punctuation, normalize each sentence, and scan the quote's whole in-sentence prefix for negators. Bias is fail-closed as everywhere in the contour: a false 🟡 is acceptable, a false 🔵 is not.

**Interfaces:**
- Consumes: existing `_norm`, `MIN_QUOTE_WORDS`, `_load_chunks` records (raw `text` field preserved).
- Produces: `_crop_severs_negation(q_norm: str, raw_text: str) -> bool` — signature changes from `(q, chunk_norm)`; only caller is `best_match`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fidelity_negation_crop.py` (if the file defines its own synthetic-corpus helper, reuse it instead of `_mk_advisor` below):

```python
import json

def _mk_advisor(tmp_path, text, tier="P1"):
    d = tmp_path / "adv"
    d.mkdir(exist_ok=True)
    with open(d / "corpus.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"source": "t", "tier": tier, "text": text},
                            ensure_ascii=False) + "\n")
    return str(d)

def test_contraction_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "You can't win by cheating. Play straight and win.")
    assert fidelity.marker_status("win by cheating", adv)["status"] == "🟡"

def test_distant_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "He did not in any real sense believe in omens or dreams.")
    assert fidelity.marker_status("believe in omens", adv)["status"] == "🟡"

def test_without_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "Without cruelty when the state is new it may stand.")
    assert fidelity.marker_status("cruelty when the state", adv)["status"] == "🟡"

def test_negation_in_other_sentence_still_blue(tmp_path):
    # «not» в СОСЕДНЕМ предложении не должно топить честную цитату (recall-контроль)
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "It is not right. Do the right thing wholly.")
    assert fidelity.marker_status("do the right thing", adv)["status"] == "🔵"

def test_clean_quote_unaffected(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "The impediment to action advances action.")
    assert fidelity.marker_status("the impediment to action", adv)["status"] == "🔵"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_fidelity_negation_crop.py -q`
Expected: the first three FAIL (status `🔵` today — that IS the C2 bug, reproduced); the two control tests PASS.

- [ ] **Step 3: Implement the guard**

In `scripts/engine/fidelity.py` replace `_NEG`/`_crop_severs_negation` (lines 21-33) with:

```python
# Токены-отрицания (C1+C2): обрезка, отсекающая ведущее отрицание, переворачивает смысл
# цитаты. «t» — хвост контракций после _norm («don't»→«don t»); «nt» оставлен бэк-компатно.
_NEG = {"not", "no", "never", "nt", "t", "cannot", "without", "nor",
        "не", "ни", "нет", "никогда", "никто", "нельзя", "без", "вовсе"}

# Разделители предложений: скоуп гарда — предложение (см. ниже).
_SENT_SPLIT = re.compile(r"[.!?…;:\n»«\"“”]+")


def _crop_severs_negation(q: str, raw_text: str) -> bool:
    """True, если обрезка отсекла отрицание из исходного ПРЕДЛОЖЕНИЯ (C2).

    _norm стирает пунктуацию, поэтому гард по окну токенов двойно ошибался: пропускал
    дистанционное «did not in any real sense believe…» (ложный 🔵) и топил бы цитаты
    из-за «not» в СОСЕДНЕМ предложении (ложный 🟡). Режем СЫРОЙ текст на предложения,
    каждое нормализуем; префикс q внутри его предложения сканируем ЦЕЛИКОМ по _NEG.
    Есть хотя бы одно чистое вхождение → False (🔵 легитимен). q через шов предложений
    (не найден ни в одном) → False: это честная дословная подстрока by design.
    Оба аргумента: q норм. (_norm), raw_text — НЕнормализованный."""
    found = False
    for sent in _SENT_SPLIT.split(raw_text or ""):
        ns = _norm(sent)
        i = ns.find(q) if ns else -1
        if i < 0:
            continue
        found = True
        if not any(tok in _NEG for tok in ns[:i].split()):
            return False                       # чистое вхождение без отрицания в префиксе
    return found                               # все вхождения с отрицанием → обрезка
```

And update the call in `best_match` (line 104) to pass the RAW text:

```python
        if q in ch["_norm"] and not _crop_severs_negation(q, ch.get("text") or ""):
```

- [ ] **Step 4: Run the file's tests, then the contour cluster**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_fidelity_negation_crop.py tests/test_fidelity_gate.py tests/test_marker_status_single_source.py tests/test_eval.py -q`
Expected: all PASS. Any pre-existing test that pinned a negation-adjacent quote as 🔵 was pinning the bug — inspect before adjusting, report to owner.

- [ ] **Step 5: Offline suite + commit (owner-gated)**

Run full offline invariant (see header). Then STOP and ask owner to commit:
`scripts/engine/fidelity.py tests/test_fidelity_negation_crop.py`
Suggested message: `fix(moat): C2 — negation-гард по скоупу предложения (контракции/дистанция/without)`

---

## PHASE 2 — C1+H5+H6: surface unity (moat on the MCP surface, doc truth)

### Task 2.1: Rule 18 (диссент / рейм-чек / diversity / never_quote) into INSTRUCTIONS

**Files:**
- Modify: `scripts/mcp_server.py` (INSTRUCTIONS, after rule 17 block, before `RESPONSE LANGUAGE`, ~line 2733)
- Test: `tests/test_mcp_server.py` (append near the existing INSTRUCTIONS content pins, ~line 203-215)
- Regen: `docs/selfdoc/index.json`, `docs/MANUAL.md`
- Docs: `SKILL.md:91` (mirror note), `docs/selfdoc/narrative/30-architecture.md:4`

**Interfaces:**
- Produces: INSTRUCTIONS rules become 0-18. `gen_selfdoc.extract_rules()` picks the new rule up automatically; counts in selfdoc index/MANUAL update via regen (final step).

- [ ] **Step 1: Write the failing test**

```python
def test_instructions_rule18_moat_directives():
    import mcp_server as m
    assert "18." in m.INSTRUCTIONS
    for kw in ("ДИССЕНТ", "РЕЙМ-ЧЕК", "never_quote", "diversity_check", "эхо-камер"):
        assert kw in m.INSTRUCTIONS, "INSTRUCTIONS не несёт ров-директиву: %s" % kw
```

Run it — Expected: FAIL (keywords absent today — that IS C1).

- [ ] **Step 2: Add Rule 18 to INSTRUCTIONS**

Insert into `scripts/mcp_server.py` after the rule-17 block, keeping the established imperative style:

```
18. ДИССЕНТ, РЕЙМ-ЧЕК, РАЗНООБРАЗИЕ, NEVER_QUOTE (анти-поддакивание — ров «не хор одинаковых»).
   (а) Советники инстанцируются в 3-м лице по role_framing персоны («X — независимый мыслитель,
       не ассистент»), НЕ как «ты-помощник». Если юзер неправ по фреймворку фигуры — скажи прямо.
       ЗАПРЕЩЕНО аффирмить обе стороны и поддакивать ради приятности. Диссент ДОЗИРУЙ и
       обосновывай: бей по сути (вывод/рамка), не механически на каждом ходу.
   (б) РЕЙМ-ЧЕК премисы ПЕРЕД ответом: какую неявную предпосылку вопрос берёт за данность? чей
       это фрейм (среды/оппонента — не юзера)? ради какой ЦЕЛИ (телос) — и сама цель стоит ли?
       Премиса крепкая — подтверди одной строкой и иди дальше; ложная — веди С реймового хода.
       Дозируй: не у каждого вопроса ложная премиса.
   (в) КОМПОЗИЦИЯ СОВЕТА: при созыве зови diversity_check(advisor_dirs) — diversity < 0.5 или
       дубль-голоса = эхо-камера: предупреди юзера и предложи контр-голос по непокрытой оси;
       «совет» из клонов молча не проводи.
   (г) NEVER_QUOTE: у части персон в persona.md есть список известных фейк-цитат (never_quote).
       Цитату оттуда НИКОГДА не выдавай (даже 🟡 с атрибуцией) — честно скажи, что это
       известная мисатрибуция.
```

- [ ] **Step 3: Update the two rule-count references**

`SKILL.md:91`: «Канон правил 0-17» → «Канон правил 0-18».
`docs/selfdoc/narrative/30-architecture.md:4`: «(правила 0–14)» → «(правила 0–18)» — this also fixes the stale H6 count.

- [ ] **Step 4: Regen selfdoc + run tests**

Run: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`
Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_mcp_server.py tests/test_selfdoc_fresh.py tests/test_no_dark_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (owner-gated)**

`scripts/mcp_server.py tests/test_mcp_server.py SKILL.md docs/selfdoc/ docs/MANUAL.md`
Suggested: `feat(moat): C1 — правило 18 (диссент/рейм-чек/diversity/never_quote) в INSTRUCTIONS`

### Task 2.2: `diversity_check` as an MCP tool

**Files:**
- Modify: `scripts/diversity_check.py` (extract pure `check()`)
- Modify: `scripts/mcp_server.py` (handler + TOOLS entry, near other read-only tools)
- Test: `tests/test_diversity_check_tool.py` (new)
- Regen: `docs/selfdoc/index.json`, `docs/MANUAL.md`

**Interfaces:**
- Produces: `diversity_check.check(paths: list[str]) -> dict` with keys `advisors`, `pairs` (each `{a, b, similarity, lenses_j, domains_j, flag}`), `diversity`, `verdict` (`ok|overlap|echo_chamber`), `missing_axes`; on bad input `{"error": ...}`. `main()` keeps its current human output, now rendered from `check()`.
- Produces: MCP tool `diversity_check(advisor_dirs: list[str])` → same dict (read-only; Rule 1 quiet). Tool count becomes 61.

- [ ] **Step 1: Write the failing test**

Create `tests/test_diversity_check_tool.py`:

```python
import os, sys, json
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server

PERSONA = "---\nname: %s\nlenses: [%s]\ndomains: [%s]\n---\nbody\n"

def _mk_advisors(root):
    specs = [("a1", "compounding, judgment-over-effort", "startups"),
             ("a2", "compounding, judgment-over-effort", "startups"),
             ("b1", "memento-mori, via-negativa", "ethics")]
    for slug, lenses, domains in specs:
        d = root / "advisors" / slug
        d.mkdir(parents=True)
        (d / "persona.md").write_text(PERSONA % (slug, lenses, domains), encoding="utf-8")

def test_diversity_tool_flags_echo_chamber(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    _mk_advisors(tmp_path)
    out = mcp_server.dispatch("diversity_check",
                              {"advisor_dirs": ["advisors/a1", "advisors/a2"]})
    assert out["verdict"] == "echo_chamber"
    assert out["diversity"] < 0.5
    assert out["pairs"][0]["flag"] == "dup"

def test_diversity_tool_healthy_board(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    _mk_advisors(tmp_path)
    out = mcp_server.dispatch("diversity_check",
                              {"advisor_dirs": ["advisors/a1", "advisors/b1"]})
    assert out["verdict"] in ("ok", "overlap")
    assert out["diversity"] >= 0.5

def test_diversity_tool_traversal_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    _mk_advisors(tmp_path)
    out = mcp_server.dispatch("diversity_check",
                              {"advisor_dirs": ["advisors/a1", "/etc"]})
    assert "error" in out
```

Run it — Expected: FAIL (`KeyError` on unknown tool).

- [ ] **Step 2: Extract `check()` in `scripts/diversity_check.py`**

Move the `axes_hint` dict to module level as `_AXES_HINT` and add:

```python
def check(paths):
    """Ортогональность состава совета → dict (без печати). paths — abs пути advisor'ов.
    <2 валидных persona.md → {"error": ...}."""
    advisors = [a for a in (load_advisor(p) for p in paths) if a]
    if len(advisors) < 2:
        return {"error": "Не нашёл persona.md минимум у двоих."}
    pairs = []
    for x, y in itertools.combinations(advisors, 2):
        lj, dj = jaccard(x["lenses"], y["lenses"]), jaccard(x["domains"], y["domains"])
        sim = (2 * lj + dj) / 3
        flag = "dup" if sim >= 0.5 else ("close" if sim >= 0.34 else "")
        pairs.append({"a": x["name"], "b": y["name"], "similarity": round(sim, 3),
                      "lenses_j": round(lj, 3), "domains_j": round(dj, 3), "flag": flag})
    mean_sim = sum(p["similarity"] for p in pairs) / len(pairs)
    diversity = round(1 - mean_sim, 3)
    verdict = ("ok" if diversity >= 0.7 else
               "overlap" if diversity >= 0.5 else "echo_chamber")
    covered = set().union(*[a["lenses"] for a in advisors])
    missing = [ax for ax, kws in _AXES_HINT.items() if not (covered & kws)]
    return {"advisors": [a["name"] for a in advisors], "pairs": pairs,
            "diversity": diversity, "verdict": verdict, "missing_axes": missing}
```

Rewrite `main()` to call `check(sys.argv[1:])` and render the existing human output from the dict (keep the current wording/verdict lines; `sys.exit(1)` paths preserved).

- [ ] **Step 3: Add the handler + TOOLS entry in `scripts/mcp_server.py`**

Near `_catalog_list` (~line 1735), add:

```python
def _diversity_check_tool(advisor_dirs):
    """Эхо-камера-детектор состава совета (read-only). Пути клампятся read-гардом."""
    import diversity_check
    if not isinstance(advisor_dirs, list) or len(advisor_dirs) < 2:
        return {"error": "дай минимум 2 advisor_dirs"}
    resolved = []
    for d in advisor_dirs:
        r = _resolve_read(d)
        if r is None or not os.path.isdir(r):
            return {"error": "advisor_dir вне корня репо или не существует: %r" % (d,)}
        resolved.append(r)
    return diversity_check.check(resolved)
```

And in `TOOLS` (any position — but keep dict order stable for diff hygiene, e.g. after `catalog_verify`):

```python
    "diversity_check": {
        "description": "Ортогональность состава совета (read-only, эхо-камера-детектор): "
                       "diversity 0..1, дубли-голоса (similarity >= 0.5 → flag=dup), непокрытые "
                       "оси мышления. ОБЯЗАТЕЛЬНО перед созывом совета (правило 18в): "
                       "diversity < 0.5 = эхо-камера — предупреди юзера, предложи контр-голос.",
        "input_schema": {"type": "object",
                         "properties": {"advisor_dirs": {"type": "array",
                                                        "items": {"type": "string"}}},
                         "required": ["advisor_dirs"]},
        "handler": _diversity_check_tool,
    },
```

- [ ] **Step 4: Regen selfdoc + run tests**

Run: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`
Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_diversity_check_tool.py tests/test_tool_dispatch_smoke.py tests/test_selfdoc_fresh.py -q`
Expected: PASS (dispatch smoke picks the new tool up automatically).

- [ ] **Step 5: Commit (owner-gated)**

`scripts/diversity_check.py scripts/mcp_server.py tests/test_diversity_check_tool.py docs/selfdoc/ docs/MANUAL.md`
Suggested: `feat(tools): H5 — diversity_check как MCP-тул (Шаг 0б доступен чистым MCP-хостам)`

### Task 2.3: Doc-honesty pass (counters, links, contradictions)

**Files:**
- Modify: `SKILL.md` (lines 26, 287-290, 470), `CHANGELOG.md` (0.1.0 lens mislabel)

No testable behavior — verify by grep; the narrative guard lands in Task 2.4.

- [ ] **Step 1: Fix the stale tool count**

`SKILL.md:470`: replace «весь цикл как MCP-тулы (37 шт.)» with «весь цикл как MCP-тулы (актуальный состав — `explain_self` / tools/list, не число в доке)». Rationale: any hardcoded count rots again; the selfdoc index is the source of truth.

- [ ] **Step 2: Fix the hybrid contradiction**

`SKILL.md:287-290` currently says FULL = HybridEngine by default — false (code default is `SemanticEngine`; `resolve_engine` picks hybrid only at `retrieval_mode=hybrid`, `engine/__init__.py:212-219`). Replace the paragraph with:

```
Движок выбирается автоматически (resolve_engine): FULL = **SemanticEngine** (bge-m3),
если ollama доступен, иначе SIMPLE-пол (лексика, 0 установки). Гибрид (bge-m3 ∪ лексика
через RRF) — **opt-in** (`retrieval_mode=hybrid`), НЕ дефолт FULL (см. «Инициализация» выше).
Защитный контур (fidelity, verbatim-чек) работает на ЛЮБОМ тире — деградирует только
качество ретрива, не честность. Диагностика: `python3 scripts/doctor.py`.
```

(This also removes the reference to the nonexistent `scripts/diagnose_retrieval.py`.)

- [ ] **Step 3: Fix the broken ARCHITECTURE link**

`SKILL.md:26`: `../ARCHITECTURE-personal-board-skill.md` → `docs/dev/ARCHITECTURE-personal-board-skill.md` (verify the target exists with Glob first; if it was renamed, link the current name).

- [ ] **Step 4: Fix the CHANGELOG lens mislabel**

`CHANGELOG.md:45` (0.1.0 section): «grounded-линза „Стратег (McKinsey)“» → «grounded-линза „Стратег (Сунь-цзы, Giles 1910, PD)“». Factual correction to a released note (Стратег is the Sun Tzu corpus lens; `mckinsey-strategy.md` is a separate frame-lens) — flag the history edit to the owner at commit time.

- [ ] **Step 5: Verify + commit (owner-gated)**

Run: `grep -n "37 шт" SKILL.md; grep -n "diagnose_retrieval" SKILL.md; grep -rn "правила 0–14" docs/` — expect no matches.
Commit: `SKILL.md CHANGELOG.md` — suggested: `docs(honesty): H6 — счётчики/ссылки/гибрид-дефолт (37→selfdoc, FULL=semantic)`

### Task 2.4: Narrative counter guard (close the blind spot in test_selfdoc_fresh)

**Files:**
- Test: `tests/test_selfdoc_fresh.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_selfdoc_fresh.py`:

```python
import re

def test_narrative_counters_fresh():
    """Рукописные narrative/*.md не протухают по счётчикам: H6 показал, что
    test_manual_matches_committed проверяет ВОСПРОИЗВОДИМОСТЬ генерации, не АКТУАЛЬНОСТЬ
    нарратива (MANUAL нёс «правила 0–14» при живых 0–17, и сьют был зелёный)."""
    idx = _committed()
    rule_max = max(r["n"] for r in idx["rules"])
    tool_n = idx["meta"]["tool_count"]
    narr_dir = os.path.join(ROOT, "docs", "selfdoc", "narrative")
    for fn in sorted(os.listdir(narr_dir)):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(narr_dir, fn), encoding="utf-8").read()
        for m in re.finditer(r"правил[а-я]*\s+0\s*[–—-]\s*(\d+)", text):
            assert int(m.group(1)) == rule_max, \
                "%s: «правила 0–%s» протухло (живых 0–%d)" % (fn, m.group(1), rule_max)
        for m in re.finditer(r"\b(\d+)\s*тул(?:ов|а)?\b", text):
            assert int(m.group(1)) == tool_n, \
                "%s: «%s тулов» протухло (живых %d)" % (fn, m.group(1), tool_n)
```

- [ ] **Step 2: Run to verify it fails (pre-Task-2.1 state) or passes (post)**

Depending on execution order this test either fails on the stale «0–14» narrative (good — it caught H6) or passes after Task 2.1's narrative fix. Either way it must pass at phase end. If a narrative uses a legitimate non-counter phrase matching the regex (e.g. «несколько тулов»), adjust the phrase, not the guard.

- [ ] **Step 3: Offline suite + commit (owner-gated)**

`tests/test_selfdoc_fresh.py` (+ any narrative wording adjustments).
Suggested: `test(selfdoc): H6 — гард счётчиков нарратива против index.json`

---

## PHASE 3 — H1 + M1/M2/M3: security hardening

### Task 3.1: H1 — clamp `ingest_telegram` out_path to `principis_corpus/` + no overwrite

**Files:**
- Modify: `scripts/mcp_server.py:1699-1707` (`_do_ingest`)
- Test: `tests/test_lifecycle_tools.py` (append, near the write-traversal tests ~line 216)

**Interfaces:**
- Consumes: `_resolve_under_root` (returns `(abs_path, None)` or `(None, error-dict)`).
- Behavior change: `out_path` must resolve to a file DIRECTLY inside `<root>/principis_corpus/` and must not already exist. The default (`principis_corpus/telegram.jsonl`) is unchanged (idempotent refresh allowed).

- [ ] **Step 1: Write the failing tests**

```python
def test_ingest_out_path_env_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    out = mcp_server._do_ingest("somehandle", out_path=".env")
    assert "error" in out
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET=1\n"

def test_ingest_out_path_code_overwrite_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "mcp_server.py").write_text("# code\n", encoding="utf-8")
    out = mcp_server._do_ingest("somehandle", out_path="scripts/mcp_server.py")
    assert "error" in out

def test_ingest_out_path_existing_file_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    d = tmp_path / "principis_corpus"
    d.mkdir()
    (d / "x.jsonl").write_text("{}\n", encoding="utf-8")
    out = mcp_server._do_ingest("somehandle", out_path="principis_corpus/x.jsonl")
    assert "error" in out
```

(These never reach the network: rejection happens before `ingest()` is called. A positive path test would need to stub `ingest_telegram.ingest` — optional, skip if the module's network calls make it awkward.)

Run — Expected: FAIL (today `_do_ingest` accepts all three; the first two would even overwrite — run with `tmp_path` fixtures only, NEVER against the real repo).

- [ ] **Step 2: Implement the clamp**

Replace `_do_ingest` with:

```python
def _do_ingest(handle, out_path=None):
    from ingest_telegram import ingest
    if out_path:
        op, err = _resolve_under_root(out_path)       # write-side traversal-гард
        if err:
            return err
        # H1: запись — ТОЛЬКО файл прямо в principis_corpus/ и ТОЛЬКО новый. Иначе
        # out_path=".env" молча уничтожал секреты, а out_path="scripts/mcp_server.py"
        # перезаписывал код сервера (RCE при рестарте) — гард был шире угрозы.
        corpus_dir = os.path.realpath(os.path.join(_root(), "principis_corpus"))
        if os.path.dirname(op) != corpus_dir:
            return {"error": "out_path должен быть новым файлом прямо в principis_corpus/ "
                             "(запись в код, конфиги и секреты запрещена)."}
        if os.path.exists(op):
            return {"error": "файл уже существует — перезапись запрещена: %s" % op}
    else:
        op = os.path.join(_root(), "principis_corpus", "telegram.jsonl")
    return ingest(handle, op)
```

- [ ] **Step 3: Run tests + commit (owner-gated)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_lifecycle_tools.py -q` → PASS.
Commit: `scripts/mcp_server.py tests/test_lifecycle_tools.py` — suggested: `fix(security): H1 — ingest out_path клампится к principis_corpus/, перезапись запрещена`

### Task 3.2: M1 — sensitive-path denylist in `_load_source_text` (+ dedupe the third clamp)

**Files:**
- Modify: `scripts/mcp_server.py:707-729` (`_load_source_text`)
- Test: `tests/test_lifecycle_tools.py` (append)

**Interfaces:**
- Produces: `_is_sensitive_path(rp: str) -> bool` in `mcp_server.py`; `_load_source_text` path-branch delegates its root-clamp to `_resolve_read` (removes the third copy of the guard — arch finding).

- [ ] **Step 1: Write the failing tests**

```python
def test_add_source_env_path_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path=".env")

def test_load_source_pem_key_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "server.pem").write_text("-----BEGIN\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path="server.pem")

def test_load_source_regular_file_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "book.txt").write_text("some public domain text\n", encoding="utf-8")
    text, hint, prov, lic = mcp_server._load_source_text(path="book.txt")
    assert "public domain" in text
```

Run — Expected: the first two FAIL (today the clamp lets every in-repo file through).

- [ ] **Step 2: Implement**

Near `_resolve_read` (line ~79) add:

```python
# M1: read-гарды пропускают ЛЮБОЙ файл под корнем → add_source(path=".env")/build_lens
# затягивали секрет в корпус, откуда cite/retrieve выносят его в контекст хоста.
_SENSITIVE_RE = re.compile(
    r"(^|/)(\.env[^/]*|\.git|id_rsa[^/]*|credentials[^/]*|[^/]*\.(pem|key|p12|pfx))$", re.I)


def _is_sensitive_path(rp):
    """True для секретов/ключей/VCS-метаданных — запрещены к чтению в корпус."""
    return bool(_SENSITIVE_RE.search(rp.replace(os.sep, "/")))
```

And replace the path-branch of `_load_source_text` (lines 721-726) with:

```python
    if path:
        rp = _resolve_read(path)                       # единый read-кламп (не третья копия)
        if rp is None:
            raise ValueError("path вне корня репо запрещён (traversal). Внешний файл — через text= или копию в репо.")
        if _is_sensitive_path(rp):
            raise ValueError("чтение чувствительных файлов (секреты, ключи, .git) в корпус запрещено.")
        return open(rp, encoding="utf-8").read(), os.path.basename(rp), f"file:{rp}", (license or "unknown")
```

- [ ] **Step 3: Run tests + commit (owner-gated)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_lifecycle_tools.py tests/test_read_traversal.py -q` → PASS.
Commit: `scripts/mcp_server.py tests/test_lifecycle_tools.py` — suggested: `fix(security): M1 — denylist секретов в read-path'ах корпуса + единый read-кламп`

### Task 3.3: M2a — Monte Carlo scenario cap

**Files:**
- Modify: `scripts/mc_run.py:96-108`
- Test: the MC test file covering `mc_run` input validation (locate with `grep -l "n должно быть" tests/`) — append

- [ ] **Step 1: Write the failing test**

```python
def test_n_above_cap_rejected():
    import mc_run
    m = _minimal_valid_map()           # reuse the file's existing map fixture/helper
    with pytest.raises(ValueError):
        mc_run.mc_run(m, seed=1, n=10**9)

def test_n_at_cap_accepted_boundary():
    # НЕ гонять полный прогон на капе (медленно): проверяем только, что валидация n проходит —
    # вызываем mc_run с n=1 и отдельно assert на граничное условие валидации.
    import mc_run
    assert mc_run.N_MAX == 100_000
    try:
        mc_run.mc_run(_minimal_valid_map(), seed=1, n=mc_run.N_MAX + 1)
        assert False, "n>N_MAX обязан отклоняться"
    except ValueError:
        pass
```

Run — Expected: FAIL (n=10⁹ accepted today → would hang; the test raises only after the fix).

- [ ] **Step 2: Implement**

In `scripts/mc_run.py` near `N_DEFAULT` add `N_MAX = 100_000` with a DoS comment, and replace the n-check (line 107-108) with:

```python
    if not isinstance(n, int) or isinstance(n, bool) or n < 1 or n > N_MAX:
        raise ValueError("Число сценариев n должно быть целым в [1, %d] — получено: %r. "
                         "(потолок — защита однопоточного расчёта от чрезмерного n)"
                         % (N_MAX, n))
```

- [ ] **Step 3: Run MC tests + commit (owner-gated)**

Run the MC test cluster → PASS. Commit: `scripts/mc_run.py tests/<mc test file>` — suggested: `fix(calc): M2 — потолок n≤100k в mc_run (DoS-гард)`

### Task 3.4: M2b — `cite` batch caps

**Files:**
- Modify: `scripts/mcp_server.py` `_cite` (~lines 505-521)
- Test: `tests/test_mcp_server.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_cite_query_list_capped(tmp_path, monkeypatch, capsys=None):
    # 50 формулировок в списке → внутренний пул запросов режется до 8.
    # Наблюдаемый контракт: _cite не делает >8 retrieve-проходов — патчим retrieve счётчиком.
    import mcp_server as m
    calls = {"n": 0}
    import eval as _eval
    real = _eval.retrieve
    def counting(q, adv, top_k=6):
        calls["n"] += 1
        return []
    monkeypatch.setattr(_eval, "retrieve", counting)
    adv = tmp_path / "adv"; adv.mkdir()
    (adv / "corpus.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    m._cite("advisors/adv", ["q%d" % i for i in range(50)])
    assert calls["n"] <= 8
```

(If `_cite`'s real signature differs, adapt — the cap is on the deduped `uniq_q` list and on `top_k`/`limit`.) Run — Expected: FAIL (50 retrieve passes today).

- [ ] **Step 2: Implement**

In `_cite`, at entry clamp the numerics and after dedup cap the query list:

```python
    # DoS-капы (M2): 10-МБ stdio-строка вмещает ~1e5 запросов; каждый — полный проход ретрива.
    try:
        top_k = min(max(int(top_k), 1), 32)
        limit = min(max(int(limit), 1), 16)
    except (TypeError, ValueError):
        return _cite_result([], {})
```
and after the dedup loop: `uniq_q = uniq_q[:8]` with the same comment.

- [ ] **Step 3: Run + commit (owner-gated)**

Run: `tests/test_mcp_server.py tests/test_cite*.py` (glob the real cite test names) → PASS.
Commit: `scripts/mcp_server.py tests/test_mcp_server.py` — suggested: `fix(security): M2 — капы батча cite (≤8 запросов, top_k≤32, limit≤16)`

### Task 3.5: M3 — `config_set` whitelist

**Files:**
- Modify: `scripts/mcp_server.py:607-634` (`_config_set`)
- Test: locate the existing config_set tests (`grep -rln "config_set" tests/`) — update + append

**Behavior change (breaking, owner-visible):** unknown keys are now REJECTED instead of written with a `warning`. Any existing test asserting the `warning` field must be updated.

- [ ] **Step 1: Write the failing tests**

```python
def test_config_set_rejects_unknown_key(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "board_config.json").write_text("{}", encoding="utf-8")
    out = mcp_server._config_set("relevance_gate", {"enabled": False})
    assert "rejected" in out or "error" in out
    import json as _j
    assert _j.load(open(tmp_path / "board_config.json")) == {}

def test_config_set_known_key_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "board_config.json").write_text("{}", encoding="utf-8")
    out = mcp_server._config_set("retrieval_mode", "hybrid")
    assert out.get("new") == "hybrid"
```

(If `_config_path` does not derive from `_root`, patch that instead — check its definition first.) Run — Expected: first FAILS (key written with only a warning today).

- [ ] **Step 2: Implement**

At the top of `_config_set`, before the per-key validators:

```python
    # M3: whitelist — иначе config_set("relevance_gate", {"enabled": false}) или любая
    # опечатка/инъекция молча переписывала конфиг контура (M7 покрывал лишь 2 числовых ключа).
    if key not in _KNOWN_CONFIG:
        return {"key": key, "rejected": value,
                "error": "неизвестный ключ. Известные: %s. Произвольные ключи не пишутся — "
                         "защита контура от опечаток и инъекций." % ", ".join(_KNOWN_CONFIG)}
```

- [ ] **Step 3: Update stale tests, run, commit (owner-gated)**

`grep -rn "не из известных\|warning" tests/ | grep -i config` — update any test pinning the old warning behavior. Run config + mcp_server clusters → PASS.
Commit: `scripts/mcp_server.py tests/…` — suggested: `fix(security): M3 — config_set по whitelist _KNOWN_CONFIG (fail-closed)`

### Task 3.6: M2c — federation caps

**Files:**
- Modify: `scripts/mcp_server.py:1799-1821` (`_federation_open`, `_federation_claim`)
- Test: `tests/test_federation_mcp.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
def test_federation_open_caps_plan_and_replicas(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(mcp_server, "_FED_BACKEND", None)
    out = mcp_server.dispatch("federation_open",
                              {"session_id": "s1",
                               "plan": [{"role": "r%d" % i} for i in range(500)]})
    assert "error" in out

def test_federation_claim_timeout_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(mcp_server, "_FED_BACKEND", None)
    # timeout=10**9 не должен блокировать RPC-цикл: кламп к 60с — проверяем кламп, не сон.
    import mcp_server as m
    seen = {}
    real = m._fed_claim
    def spy(backend, worker_id, roles, timeout):
        seen["timeout"] = timeout
        return {"tasks": []}
    monkeypatch.setattr(m, "_fed_claim", spy)
    m.dispatch("federation_claim", {"worker_id": "w", "timeout": 10**9})
    assert seen["timeout"] <= 60.0
```

Run — Expected: FAIL (no caps today).

- [ ] **Step 2: Implement**

```python
_FED_MAX_REPLICAS = 32
_FED_MAX_PLAN = 64
_FED_MAX_TIMEOUT = 60.0


def _federation_open(session_id, plan, replicas_default=3):
    # DoS-капы (M2): plan/replicas от хоста — без потолка это 1e9 INSERT'ов в sqlite.
    if not isinstance(plan, list) or not plan or len(plan) > _FED_MAX_PLAN:
        return {"error": "plan должен быть непустым списком ≤ %d ролей" % _FED_MAX_PLAN}
    try:
        replicas_default = int(replicas_default)
    except (TypeError, ValueError):
        replicas_default = 3
    replicas_default = max(1, min(replicas_default, _FED_MAX_REPLICAS))
    return _fed_open(_fed_backend(), session_id, plan, replicas_default)
```

and in `_federation_claim` clamp `timeout` to `[0.0, _FED_MAX_TIMEOUT]` with the same try/except coercion.

- [ ] **Step 3: Run + commit (owner-gated)**

Run: `tests/test_federation_mcp.py tests/test_federation*.py` → PASS.
Commit: `scripts/mcp_server.py tests/test_federation_mcp.py` — suggested: `fix(security): M2 — капы федерации (plan≤64, replicas≤32, timeout≤60)`

### Phase 3 gate

- [ ] Full offline suite green (header command). STOP for owner review of the phase diff.

---

## PHASE 4 — H7 + M4/M9: gate coherence & onboarding honesty

### Task 4.1: H7 — onboarding must not lead to a 🟡-only corpus

**Files:**
- Modify: `scripts/collect_common.py:267-270` (`summary`)
- Modify: `scripts/build_orchestrator.py:33` (false note)
- Modify: the MANUAL/narrative passage recommending legacy `build_advisor.py` — locate with `grep -rn "build_advisor.py" docs/selfdoc/narrative/ docs/MANUAL.md`; MANUAL is generated, so edit the narrative source and rebuild
- Modify: `scripts/doctor.py` (new check, near `check_corpus_tiering`)
- Test: `tests/test_doctor.py` (or nearest doctor test file) — append

- [ ] **Step 1: Failing doctor test for tier-less corpus**

```python
def test_doctor_flags_tierless_corpus(tmp_path):
    # corpus.jsonl без tier-полей (legacy build_advisor.py) → doctor предупреждает:
    # 🔵 структурно недостижим, а check_corpus_tiering без build.lock это не ловит.
    import doctor
    adv = tmp_path / "advisors" / "x"
    adv.mkdir(parents=True)
    (adv / "corpus.jsonl").write_text(
        json.dumps({"source": "s", "text": "some words here"}) + "\n", encoding="utf-8")
    checks = {c["name"]: c for c in doctor.run_doctor(str(tmp_path))["checks"]}
    assert "corpus-tier-fields" in checks
    assert checks["corpus-tier-fields"]["ok"] is False
```

(Adapt to `run_doctor`'s real return shape — read `scripts/doctor.py` first; the check must scan a sample of corpus records for missing `tier` keys.) Run — Expected: FAIL (check absent).

- [ ] **Step 2: Implement the doctor check + honesty fixes**

In `scripts/doctor.py`, next to `check_corpus_tiering`, add `check_corpus_tier_fields(root)`: for each `advisors/*/corpus.jsonl`, read up to the first 200 records; if records exist but none has a `tier` key → `ok=False` with hint «корпус собран legacy-путём без tier-разметки → 🔵 недостижим; пересобери: `python3 scripts/board.py build-advisor <dir>`». Wire it into the check list.

In `scripts/collect_common.py:267-270` change the «дальше» line to:

```python
    print(f"    дальше: python3 scripts/board.py build-advisor {os.path.dirname(os.path.dirname(path))} "
          f"(манифест→тиринг→корпус; legacy build_advisor.py не проставляет тиры → 🟡-only)")
```

In `scripts/build_orchestrator.py:33`:

```python
        steps.append({"step": "manifest", "ok": True,
                      "note": "нет манифеста → все чанки тиром A (🟡-only; задекларируй manifest для 🔵)"})
```

In the narrative source found by the grep, replace the legacy `build_advisor.py` recommendation with `python3 scripts/board.py build-advisor <dir>` and rebuild: `python3 scripts/build_manual.py`.

- [ ] **Step 3: Run + commit (owner-gated)**

Run: `tests/test_doctor.py tests/test_selfdoc_fresh.py` + offline suite → PASS.
Commit: the five files — suggested: `fix(onboarding): H7 — путь сборки с тирингом; doctor-чек tier-полей; честная нота манифеста`

### Task 4.2: DESIGN GATE (owner decision required) — gate coverage outside the semantic-cosine world

**Finding (M4):** `relevance_gate.gate_quote`/`gate_passage` return keep/pass-through whenever `is_semantic()` is False — so with `retrieval_mode=hybrid`, with `hybrid_alpha>0` (score is then the blend, not the calibrated cosine), and on the lexical tier with a live ollama judge, the anti-misapply judge silently protects nothing.

**Do not code before the owner picks:**

- **Option A (recommended):** judge-all policy — when a judge backend is available (ollama/host), verbatim candidates get judged regardless of retrieval engine; for `hybrid_alpha>0` the gate consumes the RAW cosine (return it as a separate field from the semantic/hybrid retrieve) so the calibrated band is never applied to the blend.
- **Option B:** honesty-only — keep behavior, but `doctor` gains a check that warns «гейт релевантности инертен в текущем режиме retrieval_mode/hybrid_alpha», and SKILL.md/MANUAL state the limitation.

Task skeleton once decided (A): failing test with `retrieval_mode=hybrid` asserting a non-answering verbatim quote is withheld → thread a `raw_score` field through `scripts/engine/semantic.py`/`hybrid.py` retrieve → gate on it → run contour cluster. Effort: medium. (B) is a 1-hour honesty patch; (A) is the real fix.

- [ ] **Step 1:** Present options to owner; record the choice in this plan's checkbox.
- [ ] **Step 2:** Implement per chosen option with TDD (test shapes above).
- [ ] **Step 3:** Offline suite + commit (owner-gated).

### Task 4.3: M9a — `EVAL_ENGINE` must not leak into the production gate

**Files:**
- Modify: `scripts/relevance_gate.py:146-154` (`is_semantic`)
- Modify: `scripts/engine/__init__.py` (~200-225 — read first; `resolve_engine` must not write `_ENGINE_CACHE` when `prefer` is passed)
- Modify: eval entrypoints that rely on the env (`grep -rn "EVAL_ENGINE" scripts/ tests/`)
- Test: `tests/test_relevance_gate.py` (append)

- [ ] **Step 1: Failing tests**

```python
def test_is_semantic_ignores_eval_engine_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_ENGINE", "lexical")
    # прод-гейт обязан смотреть на РЕАЛЬНЫЙ движок, не на eval-форс из шелла юзера
    import relevance_gate
    assert relevance_gate.is_semantic(str(tmp_path)) is False  # нет ollama → lexical
    monkeypatch.setenv("EVAL_ENGINE", "semantic")
    assert relevance_gate.is_semantic(str(tmp_path)) is False  # env не может ВКЛЮЧИТЬ семантику
```

(First assertion pins that env can't DISABLE either — with no ollama both forms must agree on False. If the fixture engine resolution differs, patch `engine.resolve_engine` with a spy and assert `prefer is None` from the production path.)

- [ ] **Step 2: Implement**

`is_semantic(advisor_dir, prefer=None)` — drop `os.getenv("EVAL_ENGINE")`; `gate_quote`/`gate_passage` gain a keyword-only `prefer=None` threaded through. Eval entrypoints pass `prefer=os.getenv("EVAL_ENGINE")` explicitly. In `engine/__init__.py`, skip the `_ENGINE_CACHE[key] = eng` write when `prefer is not None`.

- [ ] **Step 3: Run + commit (owner-gated)**

`tests/test_relevance_gate.py tests/test_serving_gate_eval.py` + offline suite → PASS.
Suggested: `fix(gate): M9 — EVAL_ENGINE только в eval-входах; prefer не протекает в кэш движка`

### Task 4.4: M9b — judge timeout + circuit breaker

**Files:**
- Modify: `scripts/relevance_judge.py` (`judge`, ~line 111; confirm the timeout kwarg name in `scripts/llm_local.py:47` first)
- Test: `tests/test_relevance_judge.py` (append)

- [ ] **Step 1: Failing tests**

```python
def test_judge_circuit_breaker(monkeypatch):
    import relevance_judge as rj
    rj._consec_fail, rj._cb_open_until = 0, 0.0
    calls = {"n": 0}
    def boom(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("ollama down")
    monkeypatch.setattr(rj.llm_local, "generate", boom)
    for _ in range(6):
        try:
            rj.judge("q", "p")
        except Exception:
            pass
    assert calls["n"] == 3          # после 3 подряд — обрыв, HTTP не зовём
    rj._consec_fail, rj._cb_open_until = 0, 0.0

def test_judge_timeout_threaded(monkeypatch):
    import relevance_judge as rj
    seen = {}
    def fake(prompt, **kw):
        seen.update(kw)
        return "2"
    monkeypatch.setattr(rj.llm_local, "generate", fake)
    rj._consec_fail, rj._cb_open_until = 0, 0.0
    assert rj.judge("q", "p") == 2
    assert seen.get("timeout", 999) <= 20
```

(If `judge` currently swallows generate's exceptions internally instead of raising, adapt: the breaker counts internal failures the same way.) Run — Expected: FAIL (no breaker, default 120s timeout).

- [ ] **Step 2: Implement**

```python
_JUDGE_TIMEOUT = 20        # сек: виснущая ollama не должна держать stdio-вызов часами
_CB_FAILS = 3              # подряд исключений → обрыв
_CB_COOLDOWN = 60.0        # сек
_consec_fail = 0
_cb_open_until = 0.0
```

In `judge`, before the HTTP call: `if _consec_fail >= _CB_FAILS and time.monotonic() < _cb_open_until: return 0` (fail-closed withhold). Wrap the `llm_local.generate(...)` call: on exception increment `_consec_fail`, arm `_cb_open_until` at threshold, re-raise; on success reset `_consec_fail = 0`. Pass `timeout=_JUDGE_TIMEOUT` to `generate` (confirm kwarg name).

- [ ] **Step 3: Run + commit (owner-gated)**

`tests/test_relevance_judge.py tests/test_relevance_gate.py` + offline suite → PASS.
Suggested: `fix(judge): M9 — таймаут 20с + circuit-breaker (3 промаха/60с) против виснущей ollama`

### Phase 4 gate

- [ ] Full offline suite green. STOP for owner review.

---

## PHASE 5 — H2/H3/H4 + M11: structural slices (design-gated, low-risk first)

These are refactors — behavior must not change. The green 1709-test suite is the safety net; run it after EVERY task, not just at phase end.

### Task 5.1: H3 — unify the `sys.path` idiom + CI grep test

**Files:**
- Modify: all `scripts/*.py` with in-function or non-standard `sys.path.insert` (worst: `scripts/governance.py:101,113,139,140,147,153,171,293,294,318,319,337,365` — also lift its in-function `import os/sys` to module top)
- Test: `tests/test_path_idiom.py` (new)

- [ ] **Step 1: Write the guard test**

```python
import os, re

def test_no_infunction_syspath_hacks():
    """sys.path.insert разрешён ТОЛЬКО на уровне модуля (первые 15 строк) — in-function
    хаки (76 мест, до 5 в одном модуле) это дрейф импортов."""
    root = os.path.join(os.path.dirname(__file__), "..", "scripts")
    bad = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            for i, line in enumerate(open(p, encoding="utf-8"), 1):
                if "sys.path.insert" in line and (i > 15 or line.startswith((" ", "\t"))):
                    bad.append("%s:%d" % (p, i))
    assert not bad, "in-function/late sys.path.insert:\n" + "\n".join(bad)
```

Run — Expected: FAIL listing current offenders.

- [ ] **Step 2: Normalize**

Per file: move the insert to the module top as the single idiom `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` (package subdirs like `engine/` keep their existing parent-dir variant); delete in-function repeats; lift `governance.py`'s in-function `import os/sys` to the top. Pure move — no logic edits.

- [ ] **Step 3: Run + commit (owner-gated)**

Guard test + full offline suite → PASS. Suggested: `refactor(imports): H3 — единый sys.path-идиом, гард от in-function хаков`

### Task 5.2: M11 — shared guard helpers (slug/unique-path/json/root)

**Files:**
- Modify: `scripts/mcp_server.py:1168-1192` vs `:1313-1330` (two near-identical slug+uniquify blocks)
- Modify: `_root()` reimplementations — `scripts/board.py:30`, `scripts/gen_selfdoc.py:11`, `scripts/relevance_gate.py:48` → delegate to `corpusbuild.paths.project_root()` (read it first; note `gen_selfdoc._root(root=None)` has a different signature — rename, don't collide)
- Optional (same commit only if trivial): `_load_json(path, default)` helper for the 17 `json.load(open(...))` sites
- Test: `tests/test_mcp_server.py` (append slug contract tests if absent)

- [ ] **Step 1:** Write/adjust tests pinning the slug+uniquify contract (valid slug passes; `../x` rejected; collision gets suffix) — they must pass BEFORE and AFTER the dedupe.
- [ ] **Step 2:** Extract `_validate_slug(slug) -> str|None` and `_unique_path_under_root(base) -> str` (module level in `mcp_server.py`); both save-map and save-card call them.
- [ ] **Step 3:** Delegate the three `_root()` copies to `corpusbuild.paths.project_root()`.
- [ ] **Step 4:** Offline suite → PASS. Commit (owner-gated): `refactor(dry): M11 — общие гарды slug/path/root без копий`

### Task 5.3: H4 — one lifecycle implementation behind CLI and MCP

**Files:**
- Create: `scripts/lifecycle.py` — home for `do_build/do_seed/do_ingest/doctor/setup_full` (moved verbatim from `mcp_server.py`)
- Modify: `scripts/mcp_server.py` (`_do_*` become thin delegates), `scripts/board.py:94-152` (commands call `lifecycle` instead of their own copies — read both sides first; presentation differences stay in the CLI layer)
- Test: existing `tests/test_lifecycle_tools.py` + board CLI tests must stay green unchanged

- [ ] **Step 1:** Move the five do-functions to `lifecycle.py` unchanged; `mcp_server` imports and re-exports as `_do_build` etc. (tests reference the old names — keep them working).
- [ ] **Step 2:** Point `board.py` commands at `lifecycle`, deleting the divergent copies.
- [ ] **Step 3:** Offline suite → PASS. Commit (owner-gated): `refactor(lifecycle): H4 — один lifecycle-модуль для CLI и MCP (дедуп фронтов)`

### Task 5.4: DESIGN GATE (owner decision) — `mcp_server.py` decomposition, first slice

**Finding (H2):** 2851 lines, ~117 functions, 7 domains; the fidelity gate, traversal guards and Rule 0 live in the same file as decision-lifecycle and ollama plumbing.

Recommended first slice (lowest coupling, per reviewer): the decisions cluster (`save/validate/run` decision map+card, ~1069-1560, ~550 lines) → `scripts/mcp_decisions.py`, with `mcp_server` re-exporting handlers so `TOOLS` and `dispatch` stay untouched. Then, if that lands clean: lifecycle/jobs (~1627-1730) → `mcp_lifecycle.py`; host-judge (~283-486) → `mcp_judge.py`; federation (~1785-1822) → `mcp_federation.py`. `server.py` remainder ≈ schema registry + INSTRUCTIONS + transport.

- [ ] **Step 1:** Owner approves the slice order (or defers the whole task — phases 1-4 stand alone).
- [ ] **Step 2:** Move ONE slice per commit, verbatim, re-export facade, offline suite after each.
- [ ] **Step 3:** Commit per slice (owner-gated): `refactor(server): H2 — выделен mcp_<domain>.py (фасад сохранён)`

### Task 5.5: M11b — `retrieve` out of `eval.py`; delete dead `_fallback_verbatim_per_chunk`

**Files:**
- Create: `scripts/engine/retrieval.py` — receives `retrieve()` (production path for cite/retrieve) from `scripts/eval.py`
- Modify: `scripts/eval.py` — imports & re-exports `retrieve` for back-compat; delete `_fallback_verbatim_per_chunk` (`eval.py:115-137`, self-described dead copy of the fidelity gate — eval must FAIL LOUDLY when engine.fidelity is unavailable, not score with a soft copy)
- Modify: `scripts/mcp_server.py:224,498` and the 6 test files doing `import eval as _eval` — switch to `engine.retrieval`
- Test: `tests/test_eval.py` stays green (its contract «eval не мягче prod-гейта» must not weaken)

- [ ] **Step 1:** Move `retrieve` verbatim; re-export from `eval.py`; update imports file by file.
- [ ] **Step 2:** Delete `_fallback_verbatim_per_chunk` and its call site (make the error loud).
- [ ] **Step 3:** Offline suite → PASS. Commit (owner-gated): `refactor(retrieval): M11 — retrieve в engine/retrieval.py, мёртвая копия гейта удалена`

### Phase 5 gate

- [ ] Full offline suite green after EVERY task. STOP for owner review.

---

## PHASE 6 — medium/low verify-first backlog

Rule for every item: reproduce or read the cited code FIRST (findings were reviewer-verified, but code moves); write the failing test; fix; run the cluster. Batch commits per letter-cluster (owner-gated). Locations as of 2026-07-20.

### 6.1 M5 — `safe_expr` int overflow escapes the RU-error contract

`scripts/safe_expr.py:202-204`: pure-int formulas with ~20 nineteen-digit literals produce a bigint ~1e360 → `float()` raises raw `OverflowError` (reproduced through `mc_run`). Fix:

```python
    def evaluator(env):
        try:
            return float(_eval_node(tree, env))
        except OverflowError:
            raise SafeExprEvalError("Число в формуле переполнило расчёт — упростите формулу "
                                    "или масштаб величин.")
```

Test: `compile_expr` a long pure-int product, call the evaluator, assert `SafeExprEvalError` (not `OverflowError`).

### 6.2 M6 — moat-gate stability + reproducible baseline

- `scripts/serving_gate_eval.py:116` (`judge_gate_efficacy`): judge via median of `n_samples` (mirror `poison_eval.py`'s approach) — single LLM-judge flip (8.3 p.p. at n=12) currently exceeds the 5 p.p. tolerance in `scripts/moat_check.py:52-55` → false-red gate. Also raise the tolerance to ≥ 1/n of the battery.
- `.gitignore:26` + `scripts/golden_meta.py:10`: answerable-golden fixtures are gitignored and LLM-generated without a seed — the moat baseline is unreproducible on a clean machine. Freeze the answerable slice into the repo (like the committed camouflage battery in `scripts/moat_battery/`) or pin seed+model of the generator. Owner decision: freezing corpora into git has size/legal implications (synthetic LLM-generated questions about PD corpora — should be safe; confirm).
- `scripts/serving_gate_eval.py:192-195`: `SCRATCHPAD` hardcodes a path in `/private/tmp/claude-501/...` — replace with an `--out` arg defaulting inside `docs/demo/`.

### 6.3 M7 — test-coverage gaps

- `scripts/mcp_server.py:2816-2847` (`_serve_stdio`): end-to-end test via `monkeypatch`ed `sys.stdin/stdout` (`io.StringIO`): oversized line → drain → `-32600` with `id=null`; broken JSON line → loop continues; notification → no response. This is the last blind spot of the main file.
- `tests/conftest.py`: FS-write sandbox mirroring the socket sandbox — post-test `git status --porcelain -uno` check (or patched `open` on write modes outside `tmp_path`) so a test forgetting `monkeypatch _root` fails loudly instead of writing into the real repo.
- `tests/test_federation_mcp.py`: one end-to-end dispatch scenario (open→claim→submit→poll→assemble) on a tmp sqlite.
- Zero-coverage modules: `scripts/diversity_check.py` (covered transitively by Task 2.2), `scripts/gen_golden.py`, `scripts/engine/multi_query.py`, `collect_pd/web/transcript` strip-logic — contract tests on synthetic inputs.
- Demo tests skip in CI (`tests/test_demo_scenarios.py:20`): commit a minimal synthetic corpus fixture (like `lenses/strategist`) so ~16 tests run in CI.

### 6.4 M8 — `_swallow` observability helper

77 `except Exception` sites; most are documented fail-closed, but audit-writer failures (`mcp_server.py:438`) vanish silently. Add `_swallow(what, fn, default)` logging to a gitignored `.consilium/swallow.log` and adopt it at the audit-critical sites first (judge audit, kernel themes). Do NOT mass-replace — only where the silence loses evidence.

### 6.5 M10 — docs mediums

- `SKILL.md:92-151` mirror rules 1-7 collide with canon 0-17 numbering («правило #4» means abstention here, круглый стол in canon): drop the numbers in the mirror (bold names only) and update the in-text `#N` refs accordingly.
- «/board команды» (`SKILL.md:20,45-51,193`): no slash-commands exist (no `.claude/commands/`) — reword as «фразы на естественном языке» or ship a commands/ dir (owner decision).
- `install-skill/SKILL.md`: dead artifact referenced by `QUICKSTART.md:79` — move to `docs/onboarding-recipe.md` without skill frontmatter and fix the link (owner decision: alternatively ship it for real).
- «Три тира» (`CHANGELOG.md:39`, landing specs): align to «два тира + opt-in hybrid» in current docs; leave released history alone except the factual lens fix from Task 2.3.

### 6.6 Low cluster (one commit, each with a pinning test where cheap)

- `scripts/relevance_judge.py:111` vs `scripts/judge_backend.py:43-47,71`: `judge_backend="api"` is a dead tier with a dishonest label — `judge()` hard-pins `allow_cloud=False`, so the «независимый (облако)» label silently degrades to ollama/withhold-all. Either thread `allow_cloud=True` when the resolved backend is `api` (owner decision: corpus text leaves the machine), or remove the tier and fix the label/doctor text.
- `scripts/mc_run.py:190`: tornado uses |Pearson| — blind to U-shaped sensitivity; switch to Spearman rank correlation or add a linearity caveat to `label` (owner decision — changes 📐 output numbers).
- `scripts/eval.py:376-391`: Youden threshold is picked and reported on the same scores — add an «in-sample» caveat to the curve report.
- `scripts/engine/fidelity.py:36-38`: `_norm` keeps ё≠е — real Russian quotes with е against a ё-corpus fall to 🟡 (recall loss); add `s.replace("ё","е")` + equivalence tests across the three `_norm` copies (`engine/lexical.py:18-20`, `engine/rrf.py:15-16`).
- `scripts/calibrate_advisor.py:92-100`: validity floor — reject calibrations with AUC < 0.8, add bootstrap CI of the threshold to `caveat`.
- Leak guards don't know `.env.*` (verified: `git check-ignore .env.local` misses): add `.env*` (with `!.env.example`) to `.gitignore:49`, `.mcpbignore:2`, `scripts/ci_bundle_guard.py:7`, `scripts/firewall_check.sh:34`.
- `scripts/ci_bundle_guard.py:26`: match forbidden patterns against basename AND full path (nested `sub/mcp.json` passes today).
- `scripts/firewall_check.sh:18-23`: advisor slugs interpolate into `grep -iE` unescaped (regex injection fails open) — switch to `grep -F` per name.
- `scripts/mcp_server.py:2801`: RPC errors leak absolute paths (`/Users/<user>/…`) to the host — generic message outward, detail to stderr.
- `scripts/mcp_server.py:447-453`: `_gate_verdict(advisor_dir=None)` raises `TypeError` outside the try — coerce `advisor_dir or ""` before `realpath`.
- `docs/dev/moat-baseline.json` (`inflated_n=1`): gate `inflated_n>0` in `scripts/moat_check.py:205-207` or document the allowance explicitly.
- `scripts/decision_card.py:246-292`: builder can emit a prediction its own validator rejects (`horizon_days=None`) — require it in the builder.
- `scripts/synth_eval.py:97-143`: validate «unanswerable» labels (auto-check «no chunk ≥ threshold») before admitting to the set.
- `scripts/mcp_server.py:296,1635`: `_PENDING_VERDICTS`/`_JOBS` die on stdio restart — accept-and-document (the retry path is already honest) or sqlite backend (owner decision).
- `scripts/mcp_server.py` TOOLS schemas: 19 `_obj` vs 30 inline — pick one idiom or document the rule (cosmetic).
- `tests/test_mcp_server.py:145`-style content pins (`tiers["P1"] == 31`) and INSTRUCTIONS phrase pins — gather into one contract-test file with a header explaining the pin policy.
- `tests/conftest.py:59`: optionally patch `socket.getaddrinfo` with a localhost whitelist (subprocess/DNS bypass of the socket guard — theoretical).

### Phase 6 gate

- [ ] Full offline suite green. STOP for owner review.

---

## FINAL — regen, changelog, suite, summary

- [ ] **Step 1:** `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py` — commit regenerated `docs/selfdoc/index.json` + `docs/MANUAL.md` if they drifted.
- [ ] **Step 2:** Update `CHANGELOG.md` [Unreleased]: Added (rule 18, diversity_check tool, doctor tier-fields check), Fixed (C2 negation guard, H1 ingest clamp, M1 secrets denylist, M2 caps, M3 config whitelist, M9 judge breaker/EVAL_ENGINE, H7 onboarding), Security section if the project convention wants one (see 0.1.0 style).
- [ ] **Step 3:** Full offline invariant run — must read `… passed, 1 skipped` (skip count may legitimately grow only via documented opt-ins).
- [ ] **Step 4:** `sh scripts/firewall_check.sh && python3 scripts/ci_bundle_guard.py` — both OK.
- [ ] **Step 5:** Report to owner: per-phase diffstat, suite output, design-gate decisions taken/deferred, any findings disproven during execution (with evidence).
