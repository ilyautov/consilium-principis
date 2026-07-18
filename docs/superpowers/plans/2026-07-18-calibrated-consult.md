# Calibrated Consult Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a deterministic anti-overreliance *instrument* — capture the user's own call+confidence BEFORE the council answers, show the shift AFTER (mirror), and accrue outcome-based calibration.

**Architecture:** New core module `scripts/calibrated_consult.py` (pure validate/build/mirror funcs, zero LLM/network, RU errors accumulated fail-closed — mirrors `decision_card.py`). Thin MCP wrappers in `scripts/mcp_server.py` persist records to `consults/*.consult.json` (mirrors the `decisions/*.card.json` pattern incl. `_resolve_under_root` traversal guard). Calibration reuses `prediction_calibration.py` (its funcs consume any dict with top-level `prediction`+`outcome`). Prediction contract reuses `decision_card.validate_prediction`/`validate_outcome`.

**Tech Stack:** Python 3.10+ stdlib only; pytest. No new dependencies.

**Design source:** `docs/superpowers/specs/2026-07-18-calibrated-consult-design.md` (commit a8a08f3).

**Project discipline (hard):**
- TDD: failing test first, then minimal impl.
- Offline invariant MUST stay green — currently **1592 passed, 1 skipped**:
  `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
- Env-touching tests use `monkeypatch`; never leak into `os.environ`.
- `consults/` in tests → `tmp_path`, never the real dir.
- Private advisor slugs NEVER in code/tests (tests are synthetic).
- NEVER `git add -A` — explicit paths only.
- Commit ONLY on explicit owner approval (firewall); do NOT push/merge without confirmation.
- After new tools: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`.
- Work in the main repo on `master` (NOT a worktree). Tasks touching `mcp_server.py` are sequential.

**Plan-time decisions (pinned; spec left these open):**
- **Resolver:** a thin 3rd tool `calibrated_consult_resolve(consult_id, outcome)` sets `outcome`, validated by `decision_card.validate_outcome` (NO Brier/MAE duplication). Spec §3.3 delegated resolver form to the plan; this stays thin (spec §8 forbids only a *full separate* resolver). Net MCP tools = **3** (open/close/resolve) — noted deviation from spec's "2", within §3.3's latitude.
- **Bad-follow (spec §4.2):** the literal "prior would have scored better" needs a prior-side prediction we do NOT capture in v1 (schema has ONE `prediction`, the posterior's — adding a second doubles friction, YAGNI). v1 realizes §4.2's intent via a **partition**: Brier over resolved consults with `followed_council=true` vs `false`. If following the council yields worse calibration, that is the overreliance signal. Reuses `prediction_calibration.brier`.

---

## File Structure

- **Create** `scripts/calibrated_consult.py` — core: schema constants, `new_consult_id`, `validate_consult`, `build_consult`, `compute_mirror`, `close_consult`, `resolve_consult`, `overreliance_journal`. One responsibility: the consult record contract + mirror math. Reuses `decision_card` (ULID, prediction/outcome gates) and `prediction_calibration` (Brier).
- **Create** `tests/test_calibrated_consult.py` — offline, synthetic, hermetic.
- **Modify** `scripts/mcp_server.py` — add `_CONSULTS_DIR`, `_load_consults`, three handlers (`_open_consult`, `_close_consult_tool`, `_resolve_consult_tool`, `_overreliance_journal_tool`) and four `TOOLS` entries. Sequential edits.
- **Modify** `.gitignore` — add `consults/`.
- **Modify** INSTRUCTIONS string in `scripts/mcp_server.py` — new "calibrated-consult mode" section. **OWNER-GATED task** (show wording, do not auto-apply).
- **Regenerate** `docs/selfdoc/index.json`, `docs/MANUAL.md` via the two selfdoc scripts.

---

### Task 1: Core — id, schema constants, prior/consult validation

**Files:**
- Create: `scripts/calibrated_consult.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibrated_consult.py
"""Calibrated Consult — анти-оверрелайанс инструмент (спека 2026-07-18-calibrated-consult-design).

Инструмент делает оверрелайанс ВИДИМЫМ (prior→совет→posterior→зеркало→калибровка), НЕ заявляет
«снижает». Гейты — зеркало decision_card.validate_card: аккумулируют ВСЕ RU-ошибки, fail-closed,
ноль LLM/сети. Тесты синтетические, офлайн, приватных слагов нет.
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import calibrated_consult as cc  # noqa: E402


def _prior(**over):
    p = {"call": "ждать релиза", "confidence": 0.6, "abstain": False}
    p.update(over)
    return p


def _min_consult(**over):
    c = {
        "schema_version": cc.SCHEMA_VERSION,
        "id": cc.new_consult_id(),
        "created": "2026-07-18",
        "kind": cc.KIND_CONSULT,
        "question": "Шипнуть публично сейчас или ждать?",
        "prior": _prior(),
        "posterior": None,
        "mirror": None,
        "prediction": None,
        "outcome": None,
        "decision_card_ref": None,
    }
    c.update(over)
    return c


def test_new_consult_id_is_ulid_shape():
    body = cc.new_consult_id()[len(cc._ID_PREFIX):]
    assert len(body) == 26, body
    assert all(ch in cc._CROCKFORD for ch in body), body


def test_new_consult_id_matches_pattern():
    assert re.fullmatch(r"cc_[A-Za-z0-9]+", cc.new_consult_id())


def test_schema_version_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", cc.SCHEMA_VERSION)


def test_valid_open_consult_passes():
    assert cc.validate_consult(_min_consult()) == []


def test_missing_question_flagged():
    assert any("вопрос" in e.lower() for e in cc.validate_consult(_min_consult(question="  ")))


def test_bad_id_pattern_flagged():
    assert any("cc_" in e for e in cc.validate_consult(_min_consult(id="whatever-1")))


def test_prior_confidence_out_of_range_flagged():
    assert any("увер" in e.lower() for e in cc.validate_consult(_min_consult(prior=_prior(confidence=1.5))))


def test_prior_confidence_nan_flagged():
    assert any("увер" in e.lower() for e in cc.validate_consult(_min_consult(prior=_prior(confidence=float("nan")))))


def test_prior_empty_call_flagged():
    assert any("позици" in e.lower() or "call" in e.lower()
               for e in cc.validate_consult(_min_consult(prior=_prior(call=""))))


def test_prior_abstain_must_be_bool():
    assert any("воздерж" in e.lower() or "abstain" in e.lower()
               for e in cc.validate_consult(_min_consult(prior=_prior(abstain="yes"))))


def test_errors_accumulate_not_first():
    bad = _min_consult(id="bad", question="", prior=_prior(confidence=2.0, call=""))
    assert len(cc.validate_consult(bad)) >= 3


def test_non_dict_consult_returns_error():
    assert cc.validate_consult(["nope"])
    assert cc.validate_consult(None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'calibrated_consult'`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/calibrated_consult.py
#!/usr/bin/env python3
"""Calibrated Consult — анти-оверрелайанс ИНСТРУМЕНТ (спека 2026-07-18-calibrated-consult-design).

Делает оверрелайанс ЧЕЛОВЕКА видимым (ров бьёт ложь МОДЕЛИ, не оверрелайанс ЧЕЛОВЕКА —
arXiv 2607.13562). Цикл: open фиксирует ПРИОР (твоя позиция+уверенность ДО совета) → совет →
close фиксирует ПОСТЕРИОР и считает ЗЕРКАЛО (сдвиг + инфляция уверенности) → resolve кладёт
исход → калибровка. НЕ заявляет «снижает оверрелайанс» (недоказуемо оффлайн) — только видит.

Дисциплина (как decision_card): fail-closed, RU-ошибки аккумулируются (не первая), ноль
LLM/сети, числа через тот же _is_number. Реюз decision_card (ULID, prediction/outcome гейты)
и prediction_calibration (Brier) — без дублирования.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from decision_map import _is_number, _nonempty_str
from decision_card import (_ulid, _CROCKFORD, _parse_date, validate_prediction,
                           validate_outcome)

SCHEMA_VERSION = "1.0.0"
KIND_CONSULT = "calibrated_consult"
_ID_PREFIX = "cc_"


def new_consult_id():
    """Стабильный ключ: cc_ + ULID (сортируется по времени). Реюз decision_card._ulid."""
    return _ID_PREFIX + _ulid()


def _valid_confidence(x):
    """Конечное число в [0,1] (не bool — bool пролез бы как 0/1)."""
    return _is_number(x) and not isinstance(x, bool) and 0.0 <= x <= 1.0


def _validate_prior(prior, errors, label="приор"):
    """Гейты одной стороны (prior/posterior): call непустой, confidence∈[0,1], abstain bool."""
    if not isinstance(prior, dict):
        errors.append("Сторона «%s» должна быть объектом {call, confidence, abstain}." % label)
        return
    if not _nonempty_str(prior.get("call")):
        errors.append("У «%s» пустая позиция (call) — зафиксируй СВОЙ ответ словами." % label)
    if not _valid_confidence(prior.get("confidence")):
        errors.append("У «%s» уверенность (confidence) — конечное число 0..1; сейчас: %r."
                      % (label, prior.get("confidence")))
    if not isinstance(prior.get("abstain"), bool):
        errors.append("У «%s» воздержание (abstain) — true|false (сказал бы «не знаю»?); "
                      "сейчас: %r." % (label, prior.get("abstain")))


def validate_consult(consult):
    """Fail-closed валидация записи консульта → список RU-ошибок ([] = валидна)."""
    if not isinstance(consult, dict):
        return ["Calibrated Consult должен быть JSON-объектом — получено: %s."
                % type(consult).__name__]
    errors = []
    if not _nonempty_str(consult.get("schema_version")):
        errors.append("У консульта нет версии схемы (schema_version).")
    cid = consult.get("id")
    if not _nonempty_str(cid) or not (cid.startswith(_ID_PREFIX)
                                      and cid[len(_ID_PREFIX):].isalnum()):
        errors.append("У консульта нет валидного id вида cc_<буквы/цифры> — сейчас: %r." % (cid,))
    if _parse_date(consult.get("created")) is None:
        errors.append("У консульта нет валидной даты создания (created, ISO YYYY-MM-DD).")
    if consult.get("kind") != KIND_CONSULT:
        errors.append("У консульта поле kind должно быть \"calibrated_consult\" — сейчас: %r."
                      % (consult.get("kind"),))
    if not _nonempty_str(consult.get("question")):
        errors.append("У консульта нет вопроса (question) — что несёшь совету.")
    _validate_prior(consult.get("prior"), errors, "приор")
    posterior = consult.get("posterior")
    if posterior is not None:
        _validate_prior(posterior, errors, "постериор")
        if isinstance(posterior, dict) and not isinstance(posterior.get("followed_council"), bool):
            errors.append("У постериора followed_council — true|false (принял ли позицию совета).")
    prediction = consult.get("prediction")
    if prediction is not None:
        validate_prediction(prediction, errors)
    outcome = consult.get("outcome")
    if outcome is not None:
        validate_outcome(outcome, prediction if isinstance(prediction, dict) else {},
                         created=consult.get("created"), errors=errors)
    return errors
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit** (ask owner first — firewall)

```bash
git add scripts/calibrated_consult.py tests/test_calibrated_consult.py
git commit -m "feat(consult): core validate — cc_ULID + fail-closed prior/consult гейты"
```

---

### Task 2: Core — `build_consult` constructor

**Files:**
- Modify: `scripts/calibrated_consult.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_consult_shape_and_valid():
    c = cc.build_consult("Шипнуть сейчас?", "ждать", 0.6, prior_abstain=False,
                         created="2026-07-18")
    assert c["kind"] == cc.KIND_CONSULT
    assert c["id"].startswith("cc_")
    assert c["prior"] == {"call": "ждать", "confidence": 0.6, "abstain": False}
    assert c["posterior"] is None and c["mirror"] is None and c["outcome"] is None
    assert cc.validate_consult(c) == []


def test_build_consult_respects_given_id_and_created():
    c = cc.build_consult("q", "call", 0.5, created="2026-01-02", consult_id="cc_FIXED1")
    assert c["id"] == "cc_FIXED1" and c["created"] == "2026-01-02"
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_build_consult_shape_and_valid -q`
Expected: FAIL — `AttributeError: module 'calibrated_consult' has no attribute 'build_consult'`.

- [ ] **Step 3: Write minimal implementation** (append to `calibrated_consult.py`)

```python
import time


def build_consult(question, prior_call, prior_confidence, prior_abstain=False,
                  created=None, consult_id=None):
    """Чистый конструктор записи (без валидации — её делает handler через validate_consult).
    created=None → сегодня (локальное время). id=None → новый cc_ULID."""
    if created is None:
        created = time.strftime("%Y-%m-%d")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": consult_id or new_consult_id(),
        "created": created,
        "kind": KIND_CONSULT,
        "question": question,
        "prior": {"call": prior_call, "confidence": prior_confidence,
                  "abstain": bool(prior_abstain)},
        "posterior": None,
        "mirror": None,
        "prediction": None,
        "outcome": None,
        "decision_card_ref": None,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/calibrated_consult.py tests/test_calibrated_consult.py
git commit -m "feat(consult): build_consult конструктор записи"
```

---

### Task 3: Core — `compute_mirror`

**Files:**
- Modify: `scripts/calibrated_consult.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
def test_mirror_confidence_delta_and_shift():
    m = cc.compute_mirror({"call": "ждать", "confidence": 0.6, "abstain": False},
                          {"call": "шипнуть", "confidence": 0.85, "abstain": False})
    assert abs(m["confidence_delta"] - 0.25) < 1e-9
    assert m["shifted"] is True
    assert m["abstention_dropped"] is False


def test_mirror_no_shift_normalized():
    # разный регистр/пробелы — та же позиция → не сдвиг
    m = cc.compute_mirror({"call": "Ждать релиза", "confidence": 0.6, "abstain": False},
                          {"call": "  ждать  релиза ", "confidence": 0.6, "abstain": False})
    assert m["shifted"] is False
    assert m["confidence_delta"] == 0.0


def test_mirror_abstention_dropped_is_core_signal():
    # был «не знаю» (abstain), после совета — уверенная позиция → ядро находки arXiv
    m = cc.compute_mirror({"call": "не знаю", "confidence": 0.2, "abstain": True},
                          {"call": "шипнуть", "confidence": 0.8, "abstain": False})
    assert m["abstention_dropped"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_mirror_confidence_delta_and_shift -q`
Expected: FAIL — no attribute `compute_mirror`.

- [ ] **Step 3: Write minimal implementation** (append; reuse `decision_map.norm` if present, else local normalize)

```python
def _norm_call(s):
    """Нормализация позиции для сравнения сдвига: lower + схлопнуть пробелы. Не показывается."""
    return " ".join(str(s or "").lower().split())


def compute_mirror(prior, posterior):
    """Зеркало на close: сдвиг позиции + инфляция уверенности + подавление воздержания.
    НЕ выносит вердикт «оверрелайанс» (сдвиг может быть честной коррекцией) — только факт."""
    delta = float(posterior.get("confidence", 0.0)) - float(prior.get("confidence", 0.0))
    return {
        "confidence_delta": delta,
        "shifted": _norm_call(prior.get("call")) != _norm_call(posterior.get("call")),
        "abstention_dropped": bool(prior.get("abstain")) and not bool(posterior.get("abstain")),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS (17 tests).

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/calibrated_consult.py tests/test_calibrated_consult.py
git commit -m "feat(consult): compute_mirror — сдвиг + инфляция уверенности + abstention_dropped"
```

---

### Task 4: Core — `close_consult` (posterior + mirror + optional prediction, fail-closed)

**Files:**
- Modify: `scripts/calibrated_consult.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
def _metric_prediction(**over):
    p = {"id": "pred_x", "kind": "metric", "statement": "платящих на 90-й день",
         "unit": "платящих", "p10": 60, "p50": 105, "p90": 180,
         "direction": "max", "horizon_days": 90}
    p.update(over)
    return p


def test_close_sets_posterior_and_mirror_immutably():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.85, posterior_abstain=False,
                              followed_council=True)
    assert closed["posterior"]["call"] == "шипнуть"
    assert closed["posterior"]["followed_council"] is True
    assert abs(closed["mirror"]["confidence_delta"] - 0.25) < 1e-9
    assert c["posterior"] is None            # исходная запись не мутируется
    assert cc.validate_consult(closed) == []


def test_close_attaches_valid_prediction():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False,
                              followed_council=False, prediction=_metric_prediction())
    assert closed["prediction"]["kind"] == "metric"
    assert cc.validate_consult(closed) == []


def test_close_rejects_bad_posterior_confidence():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    with pytest.raises(ValueError):
        cc.close_consult(c, "шипнуть", 1.4, posterior_abstain=False, followed_council=True)


def test_close_rejects_bad_prediction():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    with pytest.raises(ValueError):
        cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False, followed_council=True,
                         prediction={"kind": "metric", "p10": 200, "p50": 105, "p90": 180,
                                     "unit": "x", "direction": "max", "statement": "s",
                                     "horizon_days": 90})


def test_close_rejects_already_closed():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False, followed_council=True)
    with pytest.raises(ValueError):
        cc.close_consult(closed, "снова", 0.7, posterior_abstain=False, followed_council=True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_close_sets_posterior_and_mirror_immutably -q`
Expected: FAIL — no attribute `close_consult`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def close_consult(consult, posterior_call, posterior_confidence, posterior_abstain,
                  followed_council, prediction=None):
    """Проставить posterior+mirror(+prediction) в КОПИЮ записи, fail-closed.

    Невалидный постериор/прогноз или уже закрытый консульт → ValueError с RU-текстом,
    никакой частичной записи (зеркало decision_card.close_card)."""
    if not isinstance(consult, dict):
        raise ValueError("Консульт для закрытия должен быть объектом.")
    if consult.get("posterior") is not None:
        raise ValueError("Консульт уже закрыт (posterior заполнен) — повторно не закрываем.")
    posterior = {"call": posterior_call, "confidence": posterior_confidence,
                 "abstain": bool(posterior_abstain), "followed_council": bool(followed_council)}
    errors = []
    _validate_prior(posterior, errors, "постериор")
    if prediction is not None:
        validate_prediction(prediction, errors)
    if errors:
        raise ValueError("Закрытие не проходит гейты (fail-closed):\n- " + "\n- ".join(errors))
    closed = dict(consult)
    closed["posterior"] = posterior
    closed["mirror"] = compute_mirror(consult["prior"], posterior)
    if prediction is not None:
        closed["prediction"] = dict(prediction)
    return closed
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS (22 tests).

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/calibrated_consult.py tests/test_calibrated_consult.py
git commit -m "feat(consult): close_consult — posterior+mirror+прогноз, fail-closed, неизменяемо"
```

---

### Task 5: Core — `resolve_consult` (outcome, reuse `validate_outcome`)

**Files:**
- Modify: `scripts/calibrated_consult.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
def _closed_metric_consult():
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    return cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False,
                            followed_council=True, prediction=_metric_prediction())


def test_resolve_sets_outcome_immutably():
    closed = _closed_metric_consult()
    resolved = cc.resolve_consult(closed, {"resolved_on": "2026-10-16", "actual": 130})
    assert resolved["outcome"]["actual"] == 130
    assert closed["outcome"] is None                 # копия, не мутация
    assert cc.validate_consult(resolved) == []


def test_resolve_rejects_wrong_type_outcome():
    closed = _closed_metric_consult()
    with pytest.raises(ValueError):
        cc.resolve_consult(closed, {"resolved_on": "2026-10-16", "actual": "много"})


def test_resolve_requires_prediction():
    # без прогноза резолвить нечего (калибровке не с чем сравнивать) → fail-closed
    c = cc.build_consult("q", "ждать", 0.6, created="2026-07-18")
    closed = cc.close_consult(c, "шипнуть", 0.8, posterior_abstain=False, followed_council=True)
    with pytest.raises(ValueError):
        cc.resolve_consult(closed, {"resolved_on": "2026-10-16", "occurred": True})
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_resolve_sets_outcome_immutably -q`
Expected: FAIL — no attribute `resolve_consult`.

- [ ] **Step 3: Write minimal implementation** (append)

```python
def resolve_consult(consult, outcome):
    """Проставить outcome в КОПИЮ (fail-closed), провалидировав по прогнозу — зеркало
    decision_card.close_card. Без prediction резолвить нечего → ValueError."""
    if not isinstance(consult, dict):
        raise ValueError("Консульт для резолва должен быть объектом.")
    prediction = consult.get("prediction")
    if not isinstance(prediction, dict):
        raise ValueError("У консульта нет прогноза (prediction) — резолвить исход не с чем.")
    errs = validate_outcome(outcome, prediction, created=consult.get("created"))
    if errs:
        raise ValueError("Исход не проходит гейты (fail-closed):\n- " + "\n- ".join(errs))
    resolved = dict(consult)
    resolved["outcome"] = dict(outcome)
    return resolved
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS (25 tests).

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/calibrated_consult.py tests/test_calibrated_consult.py
git commit -m "feat(consult): resolve_consult — исход через validate_outcome, fail-closed"
```

---

### Task 6: Core — `overreliance_journal` (reuse `prediction_calibration.brier`)

**Files:**
- Modify: `scripts/calibrated_consult.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
import prediction_calibration as pc  # noqa: E402


def _event_consult(prior_ab, post_ab, prior_c, post_c, followed, prob, occurred, cid):
    c = cc.build_consult("q", "call-a", prior_c, prior_abstain=prior_ab,
                         created="2026-07-18", consult_id=cid)
    closed = cc.close_consult(c, "call-b", post_c, posterior_abstain=post_ab,
                              followed_council=followed,
                              prediction={"id": "p", "kind": "event", "statement": "s",
                                          "probability": prob, "horizon_days": 30})
    return cc.resolve_consult(closed, {"resolved_on": "2026-08-17", "occurred": occurred})


def test_overreliance_journal_counts_mirror_signals():
    consults = [
        # инфляция уверенности +0.3, воздержание подавлено, следовал совету, но неверно (prob .9, occurred False)
        _event_consult(True, False, 0.5, 0.8, True, 0.9, False, "cc_AAAA1"),
        # без инфляции, не следовал, верно
        _event_consult(False, False, 0.6, 0.6, False, 0.7, True, "cc_BBBB2"),
    ]
    j = cc.overreliance_journal(consults, min_n=1)
    assert j["n_closed"] == 2
    assert abs(j["confidence_inflation"] - 0.15) < 1e-9      # mean(0.3, 0.0)
    assert j["abstention_suppressed"] == 1
    # bad-follow: калибровка followed=true хуже, чем followed=false (реюз Brier)
    assert j["followed"]["brier"] is not None and j["independent"]["brier"] is not None
    assert j["followed"]["brier"] > j["independent"]["brier"]


def test_overreliance_journal_trustworthy_threshold():
    j = cc.overreliance_journal([], min_n=5)
    assert j["n_closed"] == 0 and j["trustworthy"] is False


def test_overreliance_journal_ignores_open_consults():
    open_only = cc.build_consult("q", "call", 0.6, created="2026-07-18")
    j = cc.overreliance_journal([open_only], min_n=1)
    assert j["n_closed"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_overreliance_journal_counts_mirror_signals -q`
Expected: FAIL — no attribute `overreliance_journal`.

- [ ] **Step 3: Write minimal implementation** (append; reuse `prediction_calibration`)

```python
import prediction_calibration as _pc


def _is_closed(c):
    return isinstance(c, dict) and isinstance(c.get("posterior"), dict) \
        and isinstance(c.get("mirror"), dict)


def overreliance_journal(consults, min_n=_pc.MIN_TRUSTWORTHY_N):
    """Сводка оси оверрелайанса (реюз prediction_calibration.brier — БЕЗ дублирования).

    Немедленные сигналы (нужен лишь mirror, без исхода):
      • confidence_inflation = mean(mirror.confidence_delta) по закрытым (arXiv: уверенность
        почти удваивалась);
      • abstention_suppressed = count(mirror.abstention_dropped) — ядро находки arXiv.
    Отложенный сигнал (нужен исход): bad-follow как ПАРТИЦИЯ калибровки — Brier по
    resolved-консультам с followed_council=true против false. Хуже у followed → оверрелайанс.
    (Литеральное «приор набрал бы лучше» из спеки §4.2 требует прогноза на стороне ПРИОРА,
    которого v1 не хранит — YAGNI; партиция реализует ту же интенцию.)"""
    closed = [c for c in (consults or []) if _is_closed(c)]
    n = len(closed)
    inflation = (sum(c["mirror"]["confidence_delta"] for c in closed) / n) if n else None
    suppressed = sum(1 for c in closed if c["mirror"].get("abstention_dropped"))
    followed = [c for c in closed if c["posterior"].get("followed_council")]
    independent = [c for c in closed if not c["posterior"].get("followed_council")]
    return {
        "n_closed": n,
        "trustworthy": n >= min_n,
        "confidence_inflation": inflation,
        "abstention_suppressed": suppressed,
        # реюз чистой математики: brier() читает записи с prediction+outcome (у нас они top-level)
        "followed": _pc.brier(followed),
        "independent": _pc.brier(independent),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS (28 tests).

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/calibrated_consult.py tests/test_calibrated_consult.py
git commit -m "feat(consult): overreliance_journal — инфляция/подавление + bad-follow через Brier-партицию"
```

---

### Task 7: `.gitignore` — ignore `consults/`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the entry** (find the `decisions/` line, add `consults/` next to it)

Locate the existing line (added this session, commit 972e41a):
```
decisions/
```
Add directly after it:
```
consults/
```

- [ ] **Step 2: Verify it's ignored**

Run: `mkdir -p consults && echo '{}' > consults/probe.consult.json && git status --porcelain consults/ ; rm consults/probe.consult.json`
Expected: empty output (ignored).

- [ ] **Step 3: Commit** (ask owner first)

```bash
git add .gitignore
git commit -m "chore(gitignore): consults/ — личные записи calibrated-consult (как decisions/)"
```

---

### Task 8: MCP — persistence + `calibrated_consult_open` tool

**Files:**
- Modify: `scripts/mcp_server.py` (add near the Decision Card block ~line 1155; add `TOOLS` entry ~line 1617+)
- Test: `tests/test_calibrated_consult.py`

Context: the server persists Decision Cards via `_DECISIONS_DIR`, `_SLUG_RE`, `_resolve_under_root` (write-side traversal guard), collision-suffix loop, `_root()`. Consults mirror this with `_CONSULTS_DIR = "consults"` and suffix `.consult.json`. Tools are registered in the `TOOLS` dict.

**CRITICAL dispatch contract (verified):** `dispatch(name, args)` does `TOOLS[name]["handler"](**args)` — it **keyword-expands** args. So each handler MUST be a function whose parameter names EXACTLY match the `input_schema` property names (optional props → default values), and it's registered as a **direct function reference** (like existing `"handler": _fidelity_check`), NOT a `lambda a: …`. The `tools/list` accessor is `list_tools()` (returns `[{name, description, input_schema}]`). `_resolve_under_root`/`_resolve` resolve through `_root()` dynamically, so tests redirect writes by `monkeypatch.setattr(srv, "_root", lambda: str(tmp_path))`.

- [ ] **Step 1: Write the failing test** (dispatch-level, hermetic `_root` via monkeypatch)

```python
import json  # noqa: E402  (top of test file if not already imported)
import mcp_server as srv  # noqa: E402


def _point_root(monkeypatch, tmp_path):
    """Указать сервер на временный корень доски (не трогать реальные consults/)."""
    monkeypatch.setattr(srv, "_root", lambda: str(tmp_path))


def test_open_tool_writes_record_and_returns_id(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    res = srv.dispatch("calibrated_consult_open",
                       {"question": "Шипнуть сейчас?", "prior_call": "ждать",
                        "prior_confidence": 0.6})
    assert res["ok"] is True and res["consult_id"].startswith("cc_")
    files = list((tmp_path / "consults").glob("*.consult.json"))
    assert len(files) == 1
    rec = json.load(open(files[0], encoding="utf-8"))
    assert rec["prior"]["call"] == "ждать" and rec["posterior"] is None


def test_open_tool_fail_closed_on_bad_confidence(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    res = srv.dispatch("calibrated_consult_open",
                       {"question": "q", "prior_call": "x", "prior_confidence": 5})
    assert "error" in res and res.get("errors")
    assert not list((tmp_path / "consults").glob("*.consult.json"))   # ничего не записано


def test_open_tool_listed(tmp_path, monkeypatch):
    names = {t["name"] for t in srv.list_tools()}
    assert "calibrated_consult_open" in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_open_tool_writes_record_and_returns_id -q`
Expected: FAIL — `dispatch` raises/returns unknown-tool error for `calibrated_consult_open`.

- [ ] **Step 3: Write minimal implementation**

Add after the Decision Card helpers block (after `_close_decision_card`, ~line 1350):

```python
# ── Calibrated Consult: анти-оверрелайанс инструмент (спека 2026-07-18-calibrated-consult) ──
# Тонкие обёртки ядра calibrated_consult. Пишущие тулы зовут ТОЛЬКО с согласия юзера (Rule 0).
# Артефакты — consults/*.consult.json (gitignored, личные данные).
_CONSULTS_DIR = "consults"


def _consult_slug(question):
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(question or "").lower()).strip("-")[:40] or "consult"


def _write_consult(record):
    """Записать запись consults/<created>-<slug>.consult.json под _root(), traversal-гард,
    коллизия→суффикс. → {ok, path} | {error}."""
    day = record.get("created") or time.strftime("%Y-%m-%d")
    base = os.path.join(_CONSULTS_DIR, "%s-%s" % (day, _consult_slug(record.get("question"))))
    p, err = _resolve_under_root(base + ".consult.json")
    if err:
        return err
    i = 1
    while os.path.exists(p):
        i += 1
        p, err = _resolve_under_root("%s-%d.consult.json" % (base, i))
        if err:
            return err
    rel = os.path.relpath(p, os.path.realpath(_root())).replace(os.sep, "/")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return {"ok": True, "path": rel}


def _load_consults(root):
    """Все записи consults/*.consult.json (fail-closed: битый/не-consult → пропуск).
    → [(name, record)]."""
    import calibrated_consult as ccm
    cdir = os.path.join(root, _CONSULTS_DIR)
    try:
        names = sorted(n for n in os.listdir(cdir) if n.endswith(".consult.json"))
    except OSError:
        return []
    out = []
    for name in names:
        try:
            with open(os.path.join(cdir, name), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("kind") == ccm.KIND_CONSULT:
            out.append((name, rec))
    return out


def _find_consult(root, consult_id):
    """Путь+запись по id (скан consults/). → (path, record) | (None, None)."""
    for name, rec in _load_consults(root):
        if rec.get("id") == consult_id:
            return os.path.join(root, _CONSULTS_DIR, name), rec
    return None, None


def _open_consult(question, prior_call, prior_confidence, prior_abstain=False):
    """Зафиксировать ПРИОР ДО совета (МУТИРУЮЩИЙ, Rule 0). Fail-closed валидация → отказ до записи."""
    import calibrated_consult as ccm
    record = ccm.build_consult(question, prior_call, prior_confidence,
                               prior_abstain=prior_abstain)
    errs = ccm.validate_consult(record)
    if errs:
        return {"error": "Приор не проходит гейты (fail-closed) — фиксировать нечего.",
                "errors": errs, "hint": _RELAY_AS_QUESTIONS_HINT}
    saved = _write_consult(record)
    if "error" in saved:
        return saved
    return {"ok": True, "consult_id": record["id"], "path": saved["path"],
            "next": "Теперь спроси совет как обычно. Когда получишь ответ, зафиксируй свою "
                    "позицию ПОСЛЕ через calibrated_consult_close(consult_id, …)."}
```

Then add to the `TOOLS` dict (near other entries, ~line 1617+):

```python
    "calibrated_consult_open": {
        "description": "Анти-оверрелайанс ИНСТРУМЕНТ (не совет): зафиксировать ТВОЮ позицию + "
                       "уверенность (0..1) ДО ответа совета, чтобы потом увидеть свой сдвиг. "
                       "Зови в режиме calibrated-consult ПЕРЕД тем как спросить совет. Пишет "
                       "запись (Rule 0). Затем calibrated_consult_close после ответа совета.",
        "input_schema": {"type": "object",
                         "properties": {"question": {"type": "string"},
                                        "prior_call": {"type": "string"},
                                        "prior_confidence": {"type": "number"},
                                        "prior_abstain": {"type": "boolean"}},
                         "required": ["question", "prior_call", "prior_confidence"]},
        "handler": _open_consult,   # dispatch зовёт handler(**args); имена параметров = props схемы
    },
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/mcp_server.py tests/test_calibrated_consult.py
git commit -m "feat(consult): MCP calibrated_consult_open — фиксация приора ДО совета, traversal-гард"
```

---

### Task 9: MCP — `calibrated_consult_close` tool

**Files:**
- Modify: `scripts/mcp_server.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
def test_close_tool_returns_mirror(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    opened = srv.dispatch("calibrated_consult_open",
                          {"question": "Шипнуть?", "prior_call": "ждать",
                           "prior_confidence": 0.6, "prior_abstain": True})
    cid = opened["consult_id"]
    res = srv.dispatch("calibrated_consult_close",
                       {"consult_id": cid, "posterior_call": "шипнуть",
                        "posterior_confidence": 0.85, "followed_council": True})
    assert res["ok"] is True
    assert abs(res["mirror"]["confidence_delta"] - 0.25) < 1e-9
    assert res["mirror"]["abstention_dropped"] is True
    # запись на диске обновлена
    _, rec = srv._find_consult(str(tmp_path), cid)
    assert rec["posterior"]["call"] == "шипнуть"


def test_close_tool_unknown_id_fail_closed(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    res = srv.dispatch("calibrated_consult_close",
                       {"consult_id": "cc_NOPE", "posterior_call": "x",
                        "posterior_confidence": 0.5, "followed_council": False})
    assert "error" in res


def test_close_tool_bad_prediction_fail_closed(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    cid = srv.dispatch("calibrated_consult_open",
                       {"question": "q", "prior_call": "a", "prior_confidence": 0.5})["consult_id"]
    res = srv.dispatch("calibrated_consult_close",
                       {"consult_id": cid, "posterior_call": "b", "posterior_confidence": 0.7,
                        "followed_council": True,
                        "prediction": {"kind": "event", "probability": 2.0, "statement": "s",
                                       "horizon_days": 10}})
    assert "error" in res
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_close_tool_returns_mirror -q`
Expected: FAIL — unknown tool.

- [ ] **Step 3: Write minimal implementation**

Add handler after `_open_consult`:

```python
def _close_consult_tool(consult_id, posterior_call, posterior_confidence,
                        followed_council, posterior_abstain=False, prediction=None):
    """Зафиксировать ПОСТЕРИОР после совета + вернуть ЗЕРКАЛО (МУТИРУЮЩИЙ, Rule 0).
    Fail-closed: неизвестный/закрытый id, невалидный постериор/прогноз → отказ без записи."""
    import calibrated_consult as ccm
    root = os.path.realpath(_root())
    path, rec = _find_consult(root, consult_id)
    if rec is None:
        return {"error": "Не нашёл консульт с id %s в consults/ — сначала "
                         "calibrated_consult_open." % consult_id}
    try:
        closed = ccm.close_consult(rec, posterior_call, posterior_confidence,
                                   posterior_abstain=posterior_abstain,
                                   followed_council=followed_council, prediction=prediction)
    except ValueError as e:
        return {"error": str(e), "hint": _RELAY_AS_QUESTIONS_HINT}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(closed, f, ensure_ascii=False, indent=2)
    m = closed["mirror"]
    return {"ok": True, "mirror": m,
            "note": ("Зеркало: сдвиг позиции=%s, Δуверенности=%+.2f, «не знаю» подавлено=%s. "
                     "Это НЕ вердикт «оверрелайанс» (сдвиг мог быть честной коррекцией) — "
                     "вердикт даст лишь исход. Если решение отслеживаемо, приложи prediction "
                     "и закрой исход позже через calibrated_consult_resolve."
                     % (m["shifted"], m["confidence_delta"], m["abstention_dropped"]))}
```

Add to `TOOLS`:

```python
    "calibrated_consult_close": {
        "description": "Зафиксировать ТВОЮ позицию ПОСЛЕ ответа совета + получить ЗЕРКАЛО "
                       "(сдвиг позиции, инфляция уверенности, подавлено ли «не знаю»). "
                       "followed_council: принял ли ты позицию совета. prediction (опц.): "
                       "resolvable-прогноз (контракт decision_card) для калибровки по исходу.",
        "input_schema": {"type": "object",
                         "properties": {"consult_id": {"type": "string"},
                                        "posterior_call": {"type": "string"},
                                        "posterior_confidence": {"type": "number"},
                                        "posterior_abstain": {"type": "boolean"},
                                        "followed_council": {"type": "boolean"},
                                        "prediction": {"type": "object"}},
                         "required": ["consult_id", "posterior_call", "posterior_confidence",
                                      "followed_council"]},
        "handler": _close_consult_tool,   # handler(**args); имена параметров = props схемы
    },
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/mcp_server.py tests/test_calibrated_consult.py
git commit -m "feat(consult): MCP calibrated_consult_close — постериор + зеркало, fail-closed"
```

---

### Task 10: MCP — `calibrated_consult_resolve` + `calibrated_consult_journal` tools

**Files:**
- Modify: `scripts/mcp_server.py`
- Test: `tests/test_calibrated_consult.py`

- [ ] **Step 1: Write the failing test**

```python
def _open_close_with_pred(monkeypatch, tmp_path, prob, followed):
    _point_root(monkeypatch, tmp_path)
    cid = srv.dispatch("calibrated_consult_open",
                       {"question": "q", "prior_call": "a", "prior_confidence": 0.5})["consult_id"]
    srv.dispatch("calibrated_consult_close",
                 {"consult_id": cid, "posterior_call": "b", "posterior_confidence": 0.8,
                  "followed_council": followed,
                  "prediction": {"id": "p", "kind": "event", "statement": "s",
                                 "probability": prob, "horizon_days": 30}})
    return cid


def test_resolve_tool_sets_outcome_then_journal(tmp_path, monkeypatch):
    cid = _open_close_with_pred(monkeypatch, tmp_path, 0.9, True)
    res = srv.dispatch("calibrated_consult_resolve",
                       {"consult_id": cid, "outcome": {"resolved_on": "2026-08-17",
                                                       "occurred": False}})
    assert res["ok"] is True
    j = srv.dispatch("calibrated_consult_journal", {})
    assert j["n_closed"] == 1


def test_resolve_tool_unknown_id_fail_closed(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    res = srv.dispatch("calibrated_consult_resolve",
                       {"consult_id": "cc_NOPE", "outcome": {"resolved_on": "2026-08-17",
                                                             "occurred": True}})
    assert "error" in res


def test_journal_tool_empty_is_honest(tmp_path, monkeypatch):
    _point_root(monkeypatch, tmp_path)
    j = srv.dispatch("calibrated_consult_journal", {})
    assert j["n_closed"] == 0 and j["trustworthy"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py::test_resolve_tool_sets_outcome_then_journal -q`
Expected: FAIL — unknown tool.

- [ ] **Step 3: Write minimal implementation**

Add handlers:

```python
def _resolve_consult_tool(consult_id, outcome):
    """Проставить исход консульту (МУТИРУЮЩИЙ, Rule 0). Fail-closed: неизвестный id / кривой
    исход / нет прогноза → отказ без записи."""
    import calibrated_consult as ccm
    root = os.path.realpath(_root())
    path, rec = _find_consult(root, consult_id)
    if rec is None:
        return {"error": "Не нашёл консульт с id %s в consults/." % consult_id}
    try:
        resolved = ccm.resolve_consult(rec, outcome)
    except ValueError as e:
        return {"error": str(e), "hint": _RELAY_AS_QUESTIONS_HINT}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resolved, f, ensure_ascii=False, indent=2)
    return {"ok": True, "consult_id": consult_id,
            "note": "Исход записан. Сводку оси оверрелайанса смотри calibrated_consult_journal."}


def _consult_journal_tool():
    """Сводка оси оверрелайанса по consults/ (реюз calibrated_consult.overreliance_journal).
    Малое N → trustworthy=False (честный «мало данных», не выдумка)."""
    import calibrated_consult as ccm
    root = os.path.realpath(_root())
    consults = [rec for _name, rec in _load_consults(root)]
    return ccm.overreliance_journal(consults)
```

Add to `TOOLS`:

```python
    "calibrated_consult_resolve": {
        "description": "Проставить ИСХОД консульту (когда факт лёг): outcome={resolved_on, "
                       "occurred|actual, endorsed?}. Кормит калибровку оси оверрелайанса. "
                       "Fail-closed: нужен прогноз в консульте и верный тип исхода.",
        "input_schema": {"type": "object",
                         "properties": {"consult_id": {"type": "string"},
                                        "outcome": {"type": "object"}},
                         "required": ["consult_id", "outcome"]},
        "handler": _resolve_consult_tool,   # handler(**args); имена параметров = props схемы
    },
    "calibrated_consult_journal": {
        "description": "Сводка ОСИ ОВЕРРЕЛАЙАНСА по твоим консультам: инфляция уверенности, "
                       "сколько раз «не знаю» подавлено, калибровка followed-совета против "
                       "самостоятельных. Малое N → trustworthy=false (мало данных).",
        "input_schema": _obj({}, []),
        "handler": _consult_journal_tool,   # без параметров; dispatch зовёт handler() при пустых args
    },
```

- [ ] **Step 4: Run to verify it passes**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_calibrated_consult.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (ask owner first)

```bash
git add scripts/mcp_server.py tests/test_calibrated_consult.py
git commit -m "feat(consult): MCP resolve + journal — исход и сводка оси оверрелайанса"
```

---

### Task 11: Regenerate selfdoc + manual, run full offline invariant

**Files:**
- Regenerate: `docs/selfdoc/index.json`, `docs/MANUAL.md`

- [ ] **Step 1: Regenerate selfdoc + manual**

Run:
```bash
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
```
Expected: both succeed; `git status` shows `docs/selfdoc/index.json` and `docs/MANUAL.md` modified (new module + 4 tools indexed).

- [ ] **Step 2: Run the full offline invariant**

Run:
```bash
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```
Expected: PASS — **1592 + new tests** passed, 1 skipped. If a selfdoc-freshness guard fails, re-run Step 1 (it means selfdoc wasn't regenerated).

- [ ] **Step 3: Commit** (ask owner first)

```bash
git add docs/selfdoc/index.json docs/MANUAL.md
git commit -m "docs(selfdoc): проиндексировать calibrated_consult + 4 тула"
```

---

### Task 12: INSTRUCTIONS — calibrated-consult mode section (OWNER-GATED)

**Files:**
- Modify: INSTRUCTIONS string in `scripts/mcp_server.py`

**⚠ This task does NOT auto-apply.** INSTRUCTIONS is the highest-risk surface (lesson [[antisycophancy-phase1-negative]]: text in INSTRUCTIONS gave a measured zero; firewall). The implementer MUST draft the wording, present it to the owner, and apply ONLY after explicit approval.

- [ ] **Step 1: Draft the wording** (do not apply yet)

Draft a new INSTRUCTIONS section, e.g.:

```
## Режим calibrated-consult (опционально, по запросу юзера)
Когда юзер просит «замерься» / «calibrated consult» / хочет проверить свой оверрелайанс:
1. ПЕРЕД тем как дать ответ совета, вызови calibrated_consult_open с ЕГО позицией и
   уверенностью (0..1) — зафиксируй, что он думал ДО.
2. Дай ответ совета как обычно (контур верности не меняется).
3. Вызови calibrated_consult_close с его позицией ПОСЛЕ и followed_council — покажи зеркало.
Это ИНСТРУМЕНТ видимости, НЕ заявление, что он снижает оверрелайанс. Он НЕ отменяет Правило 0
и fail-closed контур верности. Вне этого режима — обычный совет без трения.
```

- [ ] **Step 2: Present to owner, get explicit approval, then apply**

Show the draft. On approval, insert into the INSTRUCTIONS string at the appropriate mode-list location. If the owner edits wording, use theirs.

- [ ] **Step 3: Verify INSTRUCTIONS still parses + Rule 0 intact**

Run:
```bash
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```
Expected: PASS (any INSTRUCTIONS-invariant guards — Rule 0 present, min-length — stay green).

- [ ] **Step 4: Regenerate selfdoc if INSTRUCTIONS feeds it, then commit** (ask owner first)

```bash
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
git add scripts/mcp_server.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "feat(consult): INSTRUCTIONS — режим calibrated-consult (одобрено владельцем)"
```

---

## Post-Implementation

After all tasks: dispatch a final code review over the whole diff, then use **superpowers:finishing-a-development-branch**. Push/merge ONLY on explicit owner approval (firewall).
