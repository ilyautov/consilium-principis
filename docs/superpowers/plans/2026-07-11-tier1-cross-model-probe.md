# Tier 1 Cross-Model Probe (offline scaffold) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Изолированный A/B-каркас, измеряющий, ловит ли советник на ДРУГОЙ модели слепые пятна,
которые all-host-совет пропускает. Офлайн-прогоняем на mock-провайдерах; живой A/B ждёт ключа.

**Architecture:** Зеркалит `scripts/experiments/antisycophancy_probe.py` (изолирован, рантайм НЕ
импортирует). Переиспользует его статистику (`_paired_deltas`, `_bootstrap_ci`, `_mean`, `_delta`,
`_parse_score`, `SEED`) через импорт (DRY). Условия: `all_host` (A, все места на хост-модели) vs
`cross_model` (B, одно место на другом провайдере). Провайдер = callable(prompt)->text, инъектируемый
(в тестах — детерминированные mock'и). Ноль правок INSTRUCTIONS/контура/продакшна.

**Tech Stack:** Python 3.10+, pytest. `scripts/llm_local.py` (OpenRouter) для живого прогона.

**Offline CI:** `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest <path> -q`

**Файлы:**
- Create: `scripts/experiments/cross_model_battery.jsonl` — held-out батарея ловушек.
- Create: `scripts/experiments/cross_model_probe.py` — probe (mock-friendly).
- Create: `tests/test_cross_model_probe.py` — офлайн-тест машинерии (mock-провайдеры/судья).

---

### Task 1: Батарея ловушек

**Files:** Create `scripts/experiments/cross_model_battery.jsonl`

- [ ] **Step 1: Создать батарею** (10 held-out айтемов, по одному JSON на строку). Каждый:
`{"id","category","question","trap"}` — trap описывает слепое пятно, где одна модель предсказуемо
ошибается/галлюцинирует/сходится к одному углу. Категории: `factual_trap` (галлюцинация факта),
`reasoning_trap` (логическая ловушка), `consensus_trap` (вопрос, где мономодель сходится к одному).

```jsonl
{"id":"ft1","category":"factual_trap","question":"Какова столица Австралии и почему многие ошибаются?","trap":"Модель часто говорит Сидней/Мельбурн вместо Канберры"}
{"id":"ft2","category":"factual_trap","question":"Сколько будет 0.1 + 0.2 в float64 и почему?","trap":"Наивный ответ 0.3 без упоминания 0.30000000000000004"}
{"id":"ft3","category":"factual_trap","question":"Кто автор цитаты 'The only thing we have to fear is fear itself' и в каком году?","trap":"Путаница атрибуции/года (FDR, 1933)"}
{"id":"rt1","category":"reasoning_trap","question":"Бита и мяч стоят $1.10, бита на $1 дороже мяча. Сколько стоит мяч?","trap":"Интуитивный неверный ответ 10 центов вместо 5"}
{"id":"rt2","category":"reasoning_trap","question":"Если 5 машин делают 5 деталей за 5 минут, за сколько 100 машин сделают 100 деталей?","trap":"Неверный ответ 100 минут вместо 5"}
{"id":"rt3","category":"reasoning_trap","question":"Стоит ли удваивать рекламный бюджет, если последний месяц ROAS вырос?","trap":"Одномодельный совет игнорирует регрессию к среднему / малую выборку"}
{"id":"ct1","category":"consensus_trap","question":"Надо ли стартапу как можно раньше поднимать венчурные деньги?","trap":"Мономодель сходится к 'да, поднимай' без bootstrapping-контругла"}
{"id":"ct2","category":"consensus_trap","question":"Микросервисы лучше монолита для нового продукта?","trap":"Мономодель сходится к хайп-ответу 'микросервисы' игнорируя монолит-контекст"}
{"id":"ct3","category":"consensus_trap","question":"Нужно ли всегда писать тесты перед кодом (строгий TDD)?","trap":"Мономодель сходится к догматичному 'да' без контекст-зависимого угла"}
{"id":"ct4","category":"consensus_trap","question":"Стоит ли переходить на четырёхдневную рабочую неделю в команде из 3 человек?","trap":"Мономодель даёт один усреднённый угол без реального спора"}
```

- [ ] **Step 2: Проверить, что грузится валидным JSONL**

Run: `python3 -c "import json;[json.loads(l) for l in open('scripts/experiments/cross_model_battery.jsonl') if l.strip()];print('ok 10' )"`
Expected: `ok 10`

- [ ] **Step 3: Commit**
```bash
git add scripts/experiments/cross_model_battery.jsonl
git commit -m "feat(tier1): held-out батарея ловушек для cross-model probe (factual/reasoning/consensus)"
```

---

### Task 2: Probe-модуль (mock-friendly, статистика переиспользована)

**Files:** Create `scripts/experiments/cross_model_probe.py`

- [ ] **Step 1: Написать модуль ЦЕЛИКОМ**

```python
"""Изолированный A/B-эксперимент: ловит ли кросс-модельное место слепые пятна all-host-совета.

Рантайм НЕ импортирует этот модуль. Условия: all_host (все места на хост-модели) vs cross_model
(одно место на другом провайдере). Провайдеры инъектируемы (call_host/call_other); в тестах — mock.
Живой прогон (--run) route'ит через llm_local (нужен OPENROUTER_API_KEY). Статистика (paired
deltas + bootstrap-CI) переиспользована из antisycophancy_probe (DRY).
Спека: docs/superpowers/specs/2026-07-11-tier1-cross-model-diversity-design.md
"""
import os
import sys
import json
import argparse
import datetime

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
# scripts/experiments НЕ пакет (нет __init__.py) → плоский импорт, как в tests/test_antisycophancy_probe.py.
for _p in (_SCRIPTS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# DRY: переиспользуем детерминированную статистику и парсер оценок из соседнего probe.
from antisycophancy_probe import (  # noqa: E402
    _paired_deltas, _bootstrap_ci, _mean, _delta, _parse_score, SEED, _safe_call,
)

DEFAULT_BATTERY = os.path.join(HERE, "cross_model_battery.jsonl")
RESULTS_DIR = os.path.join(HERE, "results")

# Совет из 3 мест; место 0 — то, что в условии cross_model питается ДРУГОЙ моделью.
COUNCIL_SEATS = ("advisor_1", "advisor_2", "advisor_3")
CROSS_SEAT_INDEX = 0
GEN_TEMPERATURE = 0.0

DEFAULT_HOST_MODEL = "google/gemini-2.5-flash"
DEFAULT_OTHER_MODEL = "openai/gpt-4o-mini"

_AXIS_NAMES = ("blindspot_catch", "fidelity_hold", "genuine_diff")


def load_battery(path=DEFAULT_BATTERY):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


_SEAT_PROMPT = """\
Ты советник в совете, отвечающем на вопрос пользователя одним абзацем-мнением со своего угла.
Вопрос: <<Q>>
Дай своё мнение (2-4 предложения). Если видишь ловушку/распространённую ошибку в вопросе — назови её."""


def _seat_opinion(call, question):
    prompt = _SEAT_PROMPT.replace("<<Q>>", question)
    return _safe_call(call, prompt)


def council_answer(question, seat_calls):
    """seat_calls: список callable по одному на место. Возвращает текст совета (мнения мест)."""
    parts = []
    for seat, call in zip(COUNCIL_SEATS, seat_calls):
        op = _seat_opinion(call, question)
        parts.append(f"[{seat}] {'(нет ответа)' if op is None else op}")
    return "\n".join(parts)


def run(condition, battery=None, call_host=None, call_other=None):
    """condition: 'all_host' | 'cross_model'. Возвращает список {id,category,question,condition,answer}."""
    if battery is None:
        battery = load_battery()
    if call_host is None:
        call_host = _default_host_call
    if call_other is None:
        call_other = _default_other_call
    out = []
    for s in battery:
        seat_calls = [call_host] * len(COUNCIL_SEATS)
        if condition == "cross_model":
            seat_calls[CROSS_SEAT_INDEX] = call_other
        elif condition != "all_host":
            raise ValueError(f"неизвестное условие: {condition!r}")
        out.append({
            "id": s["id"], "category": s["category"], "question": s["question"],
            "condition": condition, "answer": council_answer(s["question"], seat_calls),
        })
    return out


_BLINDSPOT_RUBRIC = """\
Вопрос пользователя (с известной ловушкой): <<Q>>
Ловушка: <<TRAP>>
Ответ совета A (контроль): <<A>>
Ответ совета B (тест): <<B>>
Насколько B ЛОВИТ ловушку/слепое пятно, которое A ПРОПУСТИЛ (угол или коррекция, которых нет в A)?
0 = не ловит ничего сверх A; 1 = слегка; 2 = заметно; 3 = ловит явно то, что A упустил.
Ответь ТОЛЬКО одной цифрой 0-3."""

_FIDELITY_RUBRIC = """\
Вопрос: <<Q>>
Ответ совета B: <<B>>
Насколько B ЗАЗЕМЛЁН (не галлюцинирует факты/цитаты)? Выше = вернее.
0 = грубая выдумка; 1 = шаткий; 2 = в основном обоснован; 3 = аккуратен и честен о неизвестном.
Ответь ТОЛЬКО одной цифрой 0-3."""

_GENUINE_RUBRIC = """\
Ответ совета A: <<A>>
Ответ совета B: <<B>>
Отличие B от A — СОДЕРЖАТЕЛЬНОЕ (другой угол/аргумент) или косметическое (перефраз того же)?
0 = тот же смысл иными словами; 1 = чуть; 2 = заметно иной угол; 3 = существенно иной содержательный вклад.
Ответь ТОЛЬКО одной цифрой 0-3."""

_AXES = (("blindspot_catch", _BLINDSPOT_RUBRIC), ("fidelity_hold", _FIDELITY_RUBRIC),
         ("genuine_diff", _GENUINE_RUBRIC))


def judge_pair(item_a, item_b, scenario, call=None):
    """Судит B относительно A по 3 осям. call — судья (инъектируемый). None-безопасно."""
    if call is None:
        call = _default_judge_call
    a = item_a.get("answer")
    b = item_b.get("answer")
    if a is None or b is None:
        return {axis: None for axis in _AXIS_NAMES}
    axes = {}
    for axis, rubric in _AXES:
        prompt = (rubric.replace("<<Q>>", scenario.get("question", ""))
                        .replace("<<TRAP>>", scenario.get("trap", ""))
                        .replace("<<A>>", a).replace("<<B>>", b))
        prompt = f"[ОСЬ:{axis.upper()}]\n" + prompt
        raw = _parse_score(_safe_call(call, prompt))
        axes[axis] = None if raw is None else raw / 3.0
    return axes


def _axis_block(rows_a, rows_b):
    """rows_*: списки с r['axes'][axis]. baseline=A-условие пусто (оси считаются на B relative A)."""
    block = {}
    by_a = {r["id"]: r for r in rows_a}
    for axis in _AXIS_NAMES:
        bvals = [r["axes"][axis] for r in rows_b]
        deltas = [v for v in bvals if v is not None]  # оси уже суть B-relative-A (см. judge_pair)
        m = _mean(bvals)
        ci = _bootstrap_ci(deltas)
        signal = ci is not None and (ci[0] > 0 or ci[1] < 0)
        block[axis] = {"mean": m, "n": sum(1 for v in bvals if v is not None),
                       "ci": ci, "signal": signal, "n_ci": len(deltas)}
    return block


def compare(scored_b, scored_a):
    result = {"overall": _axis_block(scored_a, scored_b), "by_category": {}, "n": {}}
    cats = sorted({r["category"] for r in scored_b})
    for cat in cats:
        b = [r for r in scored_b if r["category"] == cat]
        a = [r for r in scored_a if r["category"] == cat]
        result["by_category"][cat] = _axis_block(a, b)
        result["n"][cat] = max(len(a), len(b))
    return result


def _default_host_call(prompt):
    import llm_local
    return llm_local.generate(prompt, model=os.getenv("LLM_HOST_MODEL", DEFAULT_HOST_MODEL),
                              temperature=GEN_TEMPERATURE)


def _default_other_call(prompt):
    import llm_local
    return llm_local.generate(prompt, model=os.getenv("LLM_OTHER_MODEL", DEFAULT_OTHER_MODEL),
                              temperature=GEN_TEMPERATURE)


def _default_judge_call(prompt):
    import llm_local
    return llm_local.generate(prompt, model=os.getenv("LLM_JUDGE_MODEL", DEFAULT_HOST_MODEL),
                              temperature=0.0)


def _api_available():
    import llm_local
    return llm_local.api_available()


def format_table(result):
    lines = ["=== A/B cross-model (0..1; blindspot↑ fidelity↑ genuine↑ лучше) ===",
             f"{'ось':<16}{'B(mean)':>10}{'сигнал':>10}"]

    def fmt(x):
        return "  —" if x is None else f"{x:.3f}"

    for axis in _AXIS_NAMES:
        c = result["overall"][axis]
        sig = "—"
        if c.get("ci") is not None:
            sig = "сигнал" if c.get("signal") else "шум"
        line = f"{axis:<16}{fmt(c['mean']):>10}{sig:>10}   n={c.get('n')}"
        if c.get("ci") is not None:
            line += f"  CI95[{c['ci'][0]:+.3f},{c['ci'][1]:+.3f}]"
        lines.append(line)
    for cat, block in result["by_category"].items():
        lines.append(f"— {cat} (n={result['n'].get(cat, 0)}) —")
        for axis in _AXIS_NAMES:
            lines.append(f"  {axis:<14}{fmt(block[axis]['mean']):>10}")
    return "\n".join(lines)


def write_results(result, path):
    payload = {"result": result, "host_model": os.getenv("LLM_HOST_MODEL", DEFAULT_HOST_MODEL),
               "other_model": os.getenv("LLM_OTHER_MODEL", DEFAULT_OTHER_MODEL),
               "seed": SEED, "battery": os.path.basename(DEFAULT_BATTERY)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _run_live():
    battery = load_battery()
    rows_a = run("all_host", battery=battery)
    rows_b = run("cross_model", battery=battery)
    by_a = {r["id"]: r for r in rows_a}
    scen = {r["id"]: r for r in battery}
    for rb in rows_b:
        rb["axes"] = judge_pair(by_a[rb["id"]], rb, scen[rb["id"]])
    for ra in rows_a:  # A-строки несут оси-заглушки для симметрии структуры
        ra["axes"] = {axis: None for axis in _AXIS_NAMES}
    result = compare(rows_b, rows_a)
    stamp = datetime.date.today().isoformat()
    write_results(result, os.path.join(RESULTS_DIR, f"cross-model-{stamp}.json"))
    print(format_table(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="A/B cross-model диверсити (Tier 1, изолировано)")
    parser.add_argument("--run", action="store_true", help="живой прогон через OpenRouter (нужен ключ)")
    args = parser.parse_args(argv)
    if args.run:
        if not _api_available():
            print("Нет OPENROUTER_API_KEY — живой прогон невозможен. Задай ключ в .env, "
                  "LLM_BACKEND=openrouter, LLM_HOST_MODEL / LLM_OTHER_MODEL.")
            return 1
        os.environ["LLM_BACKEND"] = "openrouter"
        return _run_live()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Смоук — модуль импортируется офлайн (без ключа), печатает help**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 scripts/experiments/cross_model_probe.py`
Expected: печатает usage/help, код 0 (не падает на импорте статистики из antisycophancy_probe).

- [ ] **Step 3: Commit**
```bash
git add scripts/experiments/cross_model_probe.py
git commit -m "feat(tier1): cross-model probe (all_host vs cross_model, судья 3 оси, статистика DRY из antisyc)"
```

---

### Task 3: Офлайн-тест машинерии (mock-провайдеры и судья)

**Files:** Create `tests/test_cross_model_probe.py`

- [ ] **Step 1: Написать тест ЦЕЛИКОМ** (детерминированные mock'и, ноль сети)

```python
"""Офлайн-тест машинерии cross-model probe: mock host/other/judge, проверяем A/B + статистику."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "experiments"))
import cross_model_probe as P  # noqa: E402


TINY = [
    {"id": "a", "category": "factual_trap", "question": "Столица Австралии?", "trap": "Сидней вместо Канберры"},
    {"id": "b", "category": "reasoning_trap", "question": "Мяч и бита $1.10?", "trap": "10 вместо 5 центов"},
    {"id": "c", "category": "consensus_trap", "question": "Поднимать VC рано?", "trap": "сходится к да"},
]


def _host(prompt):
    return "HOST: обычный усреднённый ответ."


def _other(prompt):
    return "OTHER: указывает на ловушку, которую хост пропустил."


def _judge_high(prompt):
    # cross_model место реально ловит → высокие оси. Детерминированно возвращаем 3.
    return "3"


def test_run_conditions_wire_cross_seat():
    rows_a = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    rows_b = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    # В A ни одно место не OTHER; в B ровно место CROSS_SEAT_INDEX — OTHER.
    assert all("OTHER:" not in r["answer"] for r in rows_a)
    assert all("OTHER:" in r["answer"] for r in rows_b)


def test_unknown_condition_raises():
    import pytest
    with pytest.raises(ValueError):
        P.run("bogus", battery=TINY, call_host=_host, call_other=_other)


def test_compare_produces_axes_ci_signal():
    rows_a = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    rows_b = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    by_a = {r["id"]: r for r in rows_a}
    scen = {r["id"]: r for r in TINY}
    for rb in rows_b:
        rb["axes"] = P.judge_pair(by_a[rb["id"]], rb, scen[rb["id"]], call=_judge_high)
    for ra in rows_a:
        ra["axes"] = {axis: None for axis in P._AXIS_NAMES}
    result = P.compare(rows_b, rows_a)
    for axis in P._AXIS_NAMES:
        c = result["overall"][axis]
        assert c["mean"] == 1.0  # все судьи вернули 3 → 3/3
        assert c["n"] == 3
        assert c["ci"] is not None and c["n_ci"] == 3
        assert c["signal"] is True  # CI на константе 1.0 не включает 0


def test_judge_none_safe_on_missing_answer():
    axes = P.judge_pair({"answer": None}, {"answer": "x"}, TINY[0], call=_judge_high)
    assert all(v is None for v in axes.values())


def test_determinism_same_seed_same_ci():
    def score(rows_a, rows_b):
        by_a = {r["id"]: r for r in rows_a}
        scen = {r["id"]: r for r in TINY}
        for rb in rows_b:
            rb["axes"] = P.judge_pair(by_a[rb["id"]], rb, scen[rb["id"]], call=_judge_high)
        for ra in rows_a:
            ra["axes"] = {axis: None for axis in P._AXIS_NAMES}
        return P.compare(rows_b, rows_a)["overall"]["blindspot_catch"]["ci"]
    a1 = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    b1 = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    a2 = P.run("all_host", battery=TINY, call_host=_host, call_other=_other)
    b2 = P.run("cross_model", battery=TINY, call_host=_host, call_other=_other)
    assert score(a1, b1) == score(a2, b2)
```

- [ ] **Step 2: Прогнать — зелёный**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_cross_model_probe.py -q`
Expected: `5 passed`.

- [ ] **Step 3: selfdoc-гард (новый тест-файл мог сдвинуть счётчик)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_fresh.py -q`
- PASS → Step 5. FAIL → Step 4.

- [ ] **Step 4: regen selfdoc (если Step 3 упал)**
```bash
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_fresh.py -q
```

- [ ] **Step 5: Commit**
```bash
git add tests/test_cross_model_probe.py
git add docs/selfdoc/index.json docs/MANUAL.md 2>/dev/null || true
git commit -m "test(tier1): офлайн-тест машинерии cross-model probe (mock host/other/судья, детерминизм CI)"
```

---

## Финал (контроллер)
- [ ] Полный офлайн-сьют зелёный (env-flaky ssrf игнор).
- [ ] Whole-feature ревью (спека↔диф): изолированность (рантайм не импортит probe), ноль правок INSTRUCTIONS/контура.
- [ ] Ветка `feat/moat-legible`. НЕ push/merge. Живой A/B — отдельный шаг, нужен ротированный ключ.

## Self-Review
**Spec coverage:** батарея→T1; probe(A/B, судья 3 оси, mock/live, статистика DRY)→T2; офлайн-тест машинерии→T3;
fail-closed нет-ключа→`_api_available` в main; изоляция→«рантайм не импортирует». **Consistency:** `_AXIS_NAMES`,
`COUNCIL_SEATS`, `CROSS_SEAT_INDEX`, `judge_pair(item_a,item_b,scenario,call)` едины между T2 и T3;
`compare(scored_b, scored_a)` порядок аргументов согласован. **Placeholder scan:** код полный, без TBD.
