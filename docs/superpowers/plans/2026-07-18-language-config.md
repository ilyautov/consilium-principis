# Языковой конфиг INSTRUCTIONS — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Выключатель `CONSILIUM_LANG` (env), фиксирующий язык ответа поверх автоподстройки en_bottom.

**Architecture:** Контур один (русский `INSTRUCTIONS` + встроенный en_bottom). При `initialize` сервер читает env `CONSILIUM_LANG` и дописывает к инструкции короткий форс-блок (`en`/`ru`) или ничего (`auto`). Форс-блок подчинён Правилу 0; перевод контура не делается.

**Tech Stack:** Python 3, чистый stdlib (`os.getenv`), pytest. Правки в `scripts/mcp_server.py`, `scripts/doctor.py`, новый `tests/test_language_config.py`.

**Спека:** `docs/superpowers/specs/2026-07-18-language-config-design.md` (коммит 31f2f81).

---

## Контекст для инженера (прочитать до начала)

- **Проблема:** `INSTRUCTIONS` (в `scripts/mcp_server.py`, ~20k символов, русский) хост читает один раз при `initialize`. Русский текст тянет ответы в русский даже на английский вопрос (замерено: 75%/57%). Блок `en_bottom` («RESPONSE LANGUAGE… answer in the language of the USER'S QUESTION») уже добавлен в конец INSTRUCTIONS (коммит 557f2cc) — это автоподстройка. Эта фича добавляет ЖЁСТКУЮ фиксацию поверх.
- **Точка внедрения:** `scripts/mcp_server.py`, функция `_handle_rpc` (строка 2200), ветка `if method == "initialize"` (2203), где сейчас `"instructions": INSTRUCTIONS` (2208). `import os` уже есть (строка 19).
- **doctor:** `scripts/doctor.py`, `run_doctor(root=".")` (строка 253) собирает `checks = [check_python(), ...]` (255). Чеки — функции, возвращающие dict `{"name","ok","detail",("advisory")}`. Образец advisory-чека — `check_skill_installed` (строка 34).
- **Импорт в тестах:** `HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,"..","scripts"))`, затем `from mcp_server import ...` / `import doctor`.
- **Офлайн-инвариант (гонять после каждой задачи):**
  `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` — сейчас **1474 passed, 1 skipped**. Не уронить.
- **Env-гигиена (МИНА):** `LLM_BACKEND=openrouter` течёт из `tests/test_antisycophancy_probe.py:221` на весь прогон. Любой тест, трогающий env, держать герметичным через `monkeypatch` — НЕ оставлять `CONSILIUM_LANG` в `os.environ` после теста. Использовать `monkeypatch.setenv`/`monkeypatch.delenv`, они откатываются сами.
- **Firewall:** коммит — только по явному разрешению владельца. НЕ пуш, НЕ мерж.
- **Приватность:** слаги приватных советников НЕ появляются в коде/тестах этой фичи.

## Структура файлов

- `scripts/mcp_server.py` — добавить два строковых константа-блока `_LANG_DIRECTIVE_EN`/`_LANG_DIRECTIVE_RU` и функцию `_response_language_directive(lang)`; в `initialize` дописать блок к INSTRUCTIONS. Ответственность: собрать финальный текст инструкции по конфигу.
- `scripts/doctor.py` — добавить `check_response_language()` и включить в список `checks`. Ответственность: показать текущий режим в диагностике.
- `tests/test_language_config.py` (новый) — гарды G1–G5. Ответственность: зафиксировать поведение и защиту от дрейфа/ослабления безопасности.

---

## Task 1: Функция форс-блока `_response_language_directive`

**Files:**
- Modify: `scripts/mcp_server.py` (рядом с определением `INSTRUCTIONS`, до `_handle_rpc`)
- Test: `tests/test_language_config.py` (создать)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_language_config.py`:

```python
"""Гарды языкового выключателя CONSILIUM_LANG. Форс-блок фиксирует язык ответа поверх
автоподстройки en_bottom, НЕ ослабляя безопасность (клауза Правила 0). Спека:
docs/superpowers/specs/2026-07-18-language-config-design.md."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import mcp_server  # noqa: E402
from mcp_server import _response_language_directive, INSTRUCTIONS  # noqa: E402


def test_en_directive_forces_english_and_bows_to_rule0():
    d = _response_language_directive("en")
    assert d, "en → непустой форс-блок"
    low = d.lower()
    assert "english" in low
    assert "rule 0" in low  # клауза подчинения безопасности

def test_ru_directive_forces_russian_and_bows_to_rule0():
    d = _response_language_directive("ru")
    assert d, "ru → непустой форс-блок"
    assert "по-русски" in d.lower()
    assert "правило 0" in d.lower()  # клауза подчинения безопасности

def test_auto_and_empty_and_junk_yield_no_directive():
    # G4 fail-safe: всё, кроме en/ru, → пустая строка (базовый en_bottom, без мусора)
    for val in ("auto", "", "  ", "EN_GB", "xyz", "english", None):
        assert _response_language_directive(val) == "", f"{val!r} должно дать пустой блок"

def test_case_and_whitespace_insensitive():
    assert _response_language_directive("  EN ") == _response_language_directive("en")
    assert _response_language_directive("Ru") == _response_language_directive("ru")
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && python3 -m pytest tests/test_language_config.py -q`
Expected: FAIL — `ImportError: cannot import name '_response_language_directive'`

- [ ] **Step 3: Реализовать функцию**

В `scripts/mcp_server.py` сразу ПОСЛЕ закрытия строки `INSTRUCTIONS = """...""" % _FEWSHOT_TEXT` (перед `def _handle_rpc`) добавить:

```python
# Форс-блоки языка ответа (выключатель CONSILIUM_LANG). Дописываются ПОСЛЕ en_bottom, поэтому
# «фиксация» перекрывает «язык вопроса» позиционно. Оба несут клаузу подчинения Правилу 0 —
# фиксация языка НЕ ослабляет безопасность/fail-closed.
_LANG_DIRECTIVE_EN = """


RESPONSE LANGUAGE OVERRIDE (never overrides Rule 0): the user has configured English output.
Answer ENTIRELY in English — headings, tier labels, service lines — regardless of the language
of any individual question. This overrides the "language of the question" rule above."""

_LANG_DIRECTIVE_RU = """


ЯЗЫК ОТВЕТА — ФИКСАЦИЯ (не перекрывает Правило 0): пользователь настроил русский вывод.
Отвечай ЦЕЛИКОМ по-русски — заголовки, лейблы тиров, служебные строки — независимо от языка
отдельного вопроса. Это перекрывает правило «язык вопроса» выше."""


def _response_language_directive(lang):
    """Форс-блок языка ответа по CONSILIUM_LANG. en → английский форс, ru → русский; auto/пусто/
    любой мусор → '' (базовый en_bottom сам подстроится под язык вопроса). Fail-safe: неизвестное
    значение НЕ роняет сервер и не инжектит мусор."""
    norm = (lang or "").strip().lower()
    if norm == "en":
        return _LANG_DIRECTIVE_EN
    if norm == "ru":
        return _LANG_DIRECTIVE_RU
    return ""
```

- [ ] **Step 4: Прогнать — проходит**

Run: `python3 -m pytest tests/test_language_config.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Коммит** (по разрешению владельца)

```bash
git add scripts/mcp_server.py tests/test_language_config.py
git commit -m "feat(lang): _response_language_directive — форс-блок языка по CONSILIUM_LANG"
```

---

## Task 2: Внедрить в `initialize` + гарды G1/G2

**Files:**
- Modify: `scripts/mcp_server.py:2203-2208` (ветка `initialize`)
- Test: `tests/test_language_config.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_language_config.py`. Функция `_handle_rpc` собирает ответ; проверяем отданные instructions через неё, с герметичным env:

```python
def _served_instructions(monkeypatch, lang):
    # lang=None → снять переменную (режим auto/unset)
    if lang is None:
        monkeypatch.delenv("CONSILIUM_LANG", raising=False)
    else:
        monkeypatch.setenv("CONSILIUM_LANG", lang)
    resp = mcp_server._handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    return resp["result"]["instructions"]

def test_initialize_en_appends_english_directive(monkeypatch):  # G1
    served = _served_instructions(monkeypatch, "en")
    assert served.startswith(INSTRUCTIONS)          # базовый контур целиком на месте
    assert served.endswith(_response_language_directive("en"))
    assert "answer entirely in english" in served.lower()

def test_initialize_ru_appends_russian_directive(monkeypatch):  # G1
    served = _served_instructions(monkeypatch, "ru")
    assert served.endswith(_response_language_directive("ru"))
    assert "отвечай целиком по-русски" in served.lower()

def test_initialize_auto_appends_nothing(monkeypatch):  # G1
    served = _served_instructions(monkeypatch, None)
    assert served == INSTRUCTIONS                    # ровно базовый контур, без довеска
    served_junk = _served_instructions(monkeypatch, "xyz")
    assert served_junk == INSTRUCTIONS               # мусор → тоже базовый (G4 на уровне initialize)

def test_rules_0_and_5_survive_every_mode(monkeypatch):  # G2
    # Правила безопасности и верности присутствуют во всех режимах — форс-блок их не вытесняет.
    for lang in ("en", "ru", None):
        served = _served_instructions(monkeypatch, lang)
        assert "0. БЕЗОПАСНОСТЬ ВЫШЕ ВСЕГО" in served, f"Rule 0 пропал в режиме {lang}"
        assert "5. КОНТУР ВЕРНОСТИ" in served, f"Rule 5 пропал в режиме {lang}"
```

> ⚠️ Маркеры Правил 0/5 (`"0. БЕЗОПАСНОСТЬ ВЫШЕ ВСЕГО"`, `"5. КОНТУР ВЕРНОСТИ"`) — проверить их точное написание в `scripts/mcp_server.py` перед запуском: `grep -n "БЕЗОПАСНОСТЬ ВЫШЕ\|КОНТУР ВЕРНОСТИ" scripts/mcp_server.py`. Если формулировка иная — подставить фактическую (это несущие правила, они там есть).

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/test_language_config.py -q`
Expected: FAIL — `test_initialize_en/ru_appends_*` падают (initialize пока отдаёт голый INSTRUCTIONS). `auto`/G2 могут проходить сразу.

- [ ] **Step 3: Внедрить**

В `scripts/mcp_server.py`, ветка `if method == "initialize"` (2203-2208), заменить:

```python
    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "consilium-principis", "version": "0.1.0"},
            "instructions": INSTRUCTIONS,
        })
```

на:

```python
    if method == "initialize":
        # Язык ответа фиксируется конфигом (env), известным серверу ещё до первого вопроса.
        instructions = INSTRUCTIONS + _response_language_directive(os.getenv("CONSILIUM_LANG"))
        return _rpc_result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "consilium-principis", "version": "0.1.0"},
            "instructions": instructions,
        })
```

- [ ] **Step 4: Прогнать — проходит**

Run: `python3 -m pytest tests/test_language_config.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Коммит** (по разрешению владельца)

```bash
git add scripts/mcp_server.py tests/test_language_config.py
git commit -m "feat(lang): initialize отдаёт INSTRUCTIONS + форс-блок по CONSILIUM_LANG"
```

---

## Task 3: Гарды G3/G5 (клауза Rule 0 и «гард не спит»)

**Files:**
- Test: `tests/test_language_config.py`

Обоснование отдельной задачи: G3 (оба блока подчинены Правилу 0) и G5 (гард ловит опустошение блока) — это защита от будущего дрейфа, а не поведение. Они не требуют правок кода — только тесты, стерегущие уже написанное.

- [ ] **Step 1: Написать тесты (должны сразу пройти на текущем коде)**

Дописать в `tests/test_language_config.py`:

```python
def test_both_force_blocks_bow_to_rule0():  # G3
    # Клауза подчинения безопасности обязана быть в ОБОИХ форс-блоках — иначе фиксация языка
    # могла бы позиционно (она последняя) перебить и Правило 0.
    en = _response_language_directive("en").lower()
    ru = _response_language_directive("ru").lower()
    assert "never overrides rule 0" in en, "EN-блок потерял клаузу подчинения Rule 0"
    assert "не перекрывает правило 0" in ru, "RU-блок потерял клаузу подчинения Правилу 0"

def test_guard_not_asleep_force_blocks_are_nonempty_and_distinct():  # G5
    # Если кто-то опустошит блок, «фиксация» станет молчаливым no-op — гард это ловит.
    en = _response_language_directive("en")
    ru = _response_language_directive("ru")
    assert len(en.strip()) > 40 and len(ru.strip()) > 40, "форс-блок схлопнулся до пустого"
    assert en != ru, "EN и RU блоки совпали — один из них потерян"
```

- [ ] **Step 2: Прогнать — проходит**

Run: `python3 -m pytest tests/test_language_config.py -q`
Expected: PASS (11 passed)

- [ ] **Step 3: Адверсариально проверить, что G3/G5 не спят**

Временно сломать (НЕ коммитить): в `scripts/mcp_server.py` убрать из `_LANG_DIRECTIVE_EN` слова `never overrides Rule 0`. Прогнать `python3 -m pytest tests/test_language_config.py::test_both_force_blocks_bow_to_rule0 -q` → ДОЛЖЕН упасть. Вернуть текст. Затем заменить тело `_LANG_DIRECTIVE_EN` на `"\n\n"` → `test_guard_not_asleep...` ДОЛЖЕН упасть. Вернуть.

> Откатывать восстановлением текста, НЕ `git checkout` (в дереве есть незакоммиченное). Отчитаться, что оба гарда упали на своей канарейке.

- [ ] **Step 4: Коммит** (по разрешению владельца)

```bash
git add tests/test_language_config.py
git commit -m "test(lang): G3 клауза Rule 0 + G5 гард-не-спит (проверены адверсариально)"
```

---

## Task 4: doctor-чек `response-language`

**Files:**
- Modify: `scripts/doctor.py` (новая `check_response_language`, включить в `checks`)
- Test: `tests/test_language_config.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_language_config.py`:

```python
def test_doctor_reports_language_mode(monkeypatch):
    import doctor
    monkeypatch.setenv("CONSILIUM_LANG", "en")
    c = doctor.check_response_language()
    assert c["name"] == "response-language"
    assert c["ok"] is True and c.get("advisory") is True   # диагностика, не блокирует здоровье
    assert "en" in c["detail"] and "CONSILIUM_LANG" in c["detail"]

def test_doctor_language_mode_defaults_to_auto(monkeypatch):
    import doctor
    monkeypatch.delenv("CONSILIUM_LANG", raising=False)
    assert "auto" in doctor.check_response_language()["detail"]
    monkeypatch.setenv("CONSILIUM_LANG", "xyz")             # мусор → auto (как в directive)
    assert "auto" in doctor.check_response_language()["detail"]
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/test_language_config.py -q`
Expected: FAIL — `AttributeError: module 'doctor' has no attribute 'check_response_language'`

- [ ] **Step 3: Реализовать чек**

В `scripts/doctor.py` добавить функцию (рядом с прочими `check_*`, напр. после `check_skill_installed`):

```python
def check_response_language():
    # Диагностика: какой язык ответа зафиксирован env CONSILIUM_LANG. advisory — режим auto
    # (умолчание) полностью рабочий, чек не роняет здоровье.
    val = (os.getenv("CONSILIUM_LANG") or "").strip().lower()
    mode = val if val in ("en", "ru") else "auto"
    return {"name": "response-language", "ok": True, "advisory": True,
            "detail": f"{mode} (CONSILIUM_LANG)"}
```

В `run_doctor` (строка ~255) включить в список `checks`:

```python
    checks = [check_python(), check_skill_installed(), check_response_language(),
              check_tier(), check_judge(),
              check_calibration(root), check_gov_anchors(root), check_corpus_tiering(root)]
```

> Проверить, что `import os` есть в `scripts/doctor.py` (`grep -n "^import os" scripts/doctor.py`). Если нет — добавить.

- [ ] **Step 4: Прогнать — проходит**

Run: `python3 -m pytest tests/test_language_config.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Коммит** (по разрешению владельца)

```bash
git add scripts/doctor.py tests/test_language_config.py
git commit -m "feat(lang): doctor показывает режим CONSILIUM_LANG (advisory)"
```

---

## Task 5: selfdoc + полный офлайн-прогон

**Files:**
- Modify: `docs/selfdoc/index.json`, `docs/MANUAL.md` (регенерация)

- [ ] **Step 1: Регенерировать selfdoc**

Новый тест-файл `tests/test_language_config.py` меняет счётчик тестов → гарды свежести selfdoc упадут без регенерации.

Run:
```bash
cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
```
Expected: файлы `docs/selfdoc/index.json` и `docs/MANUAL.md` обновлены (test_count вырос).

- [ ] **Step 2: Полный офлайн-инвариант**

Run:
```bash
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```
Expected: **1483 passed, 1 skipped** (1474 + 9 новых тестов языкового конфига; точное число сверить, главное — 0 failed и +N к базовому).

- [ ] **Step 3: Проверить env-гигиену (мина)**

Прогон не должен уйти в сеть и не должен занять минуту+. Если время скакнуло или упал `test_synth_eval` — какой-то тест оставил `CONSILIUM_LANG`/`LLM_BACKEND` в `os.environ`. Проверить, что все новые тесты используют `monkeypatch`, а не `os.environ[...] = ...`.

- [ ] **Step 4: Коммит** (по разрешению владельца)

```bash
git add docs/selfdoc/index.json docs/MANUAL.md
git commit -m "chore(lang): selfdoc после теста языкового конфига"
```

---

## Приёмка (после всех задач)

- [ ] `CONSILIUM_LANG=en` → `initialize` отдаёт INSTRUCTIONS + английский форс-блок (юнит G1 ✓).
- [ ] `CONSILIUM_LANG=ru` → русский форс-блок (юнит G1 ✓).
- [ ] не задано / мусор → голый INSTRUCTIONS, поведение en_bottom (G1/G4 ✓).
- [ ] Правила 0 и 5 присутствуют во всех режимах (G2 ✓), оба блока подчинены Rule 0 (G3 ✓, адверсариально), пустой блок ловится (G5 ✓, адверсариально).
- [ ] doctor показывает режим (advisory, не роняет здоровье).
- [ ] офлайн-инвариант зелёный, selfdoc свежий, сеть не течёт.
- [ ] **Опциональный живой замер** (вне TDD, требует ключа): `CONSILIUM_LANG=en python3 scripts/experiments/instructions_language_probe.py --run --ru-n 16` — английский путь чинится И русский вопрос ТОЖЕ уходит в английский (доказывает, что форс жёстче автоподстройки). Результат в `scripts/experiments/results/`, НЕ коммитить. Это подтверждение, не блокер мержа.

## Вне скоупа (YAGNI — спека §8)

Полный перевод контура на английский (отложен до замера шестым плечом пробы), автоопределение по локали/гео, UI выбора языка, >2 языков. НЕ реализовывать.
