# Moat Legible + Honest Offline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать ров видимым в README (проверяемая цитата как заголовочный пруф) и убрать
собственный оверклейм «работает офлайн», закрепив честность регресс-гардом.

**Architecture:** Чисто документационная работа + один тест-гард. INSTRUCTIONS/контур/сервер НЕ
трогаются (клэш-формат и citation-rendering уже в коде — Rule 3(в), Rules 5/7). TDD: сначала гард
честных клеймов (красный на текущем README), затем правки README делают его зелёным; далее
аддитивные витринные правки держат гард зелёным.

**Tech Stack:** Python 3.10+, pytest. README.md (Markdown). Офлайн-инвариант CI.

**Офлайн-прогон (всегда так):**
`HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest <path> -q`

**Контекст веток/файлов:**
- Ветка уже создана: `feat/moat-legible`. НЕ пушить, НЕ мержить.
- README.md сейчас имеет **uncommitted** блок «Что это» (строки ~22-32) с оверклеймом на строке 32.
- Оверклеймы ровно в двух местах: README:15 (бейдж), README:32 (блок «Что это»).
  Строки 76 и 143 уже корректно заужены на «контур»/«честность» — **НЕ трогать**.

---

### Task 1: Регресс-гард честных клеймов + правка офлайн-оверклейма (TDD)

**Files:**
- Create: `tests/test_readme_honest_claims.py`
- Modify: `README.md:15` (бейдж), `README.md:32` (последнее предложение блока «Что это»)
- Возможно: `docs/selfdoc/index.json`, `docs/MANUAL.md` (regen, если новый тест-файл сдвинул счётчик)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_readme_honest_claims.py`:

```python
"""Гард: README не оверклеймит «работает офлайн». Ров = строгость, поэтому клеймы честные.

Офлайн только КОНТУР честности (гейт/сверка/поиск до чистого Python). РАССУЖДЕНИЕ советников
крутится на хост-модели (в Claude Code — облако). Значит любое упоминание «офлайн» в README
должно быть заужено квалификатором, а не выдаваться за свойство всего продукта.
"""
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"

# Квалификаторы, рядом с которыми упоминание офлайна честно (в той же строке).
QUALIFIERS = ("контур", "локальн", "агент, который у тебя уже есть")


def _text():
    return README.read_text(encoding="utf-8")


def test_no_whole_product_offline_overclaim():
    """Неквалифицированный whole-product claim «Работает офлайн, без ключей» запрещён."""
    assert "Работает офлайн, без ключей" not in _text(), (
        "README оверклеймит офлайн как свойство всего продукта — рассуждение советников облачное"
    )


def test_badge_does_not_claim_offline():
    """Бейдж-строка не должна утверждать «works offline» (вводит в заблуждение)."""
    low = _text().lower()
    assert "works-offline" not in low and "works offline" not in low, (
        "Бейдж утверждает 'works offline' — убрать, оставить честный (no extra keys · no extra cost)"
    )


def test_every_offline_mention_is_qualified():
    """Каждая прозаическая строка с «офлайн»/«offline» несёт квалификатор в той же строке."""
    offenders = []
    for line in _text().splitlines():
        low = line.lower()
        if "shields.io" in low:  # бейдж-картинки покрыты отдельным тестом
            continue
        if "офлайн" in low or "offline" in low:
            if not any(q in low for q in QUALIFIERS):
                offenders.append(line.strip())
    assert not offenders, (
        "Неквалифицированное упоминание офлайна (заузь на контур/локальные модели/хост): "
        + " | ".join(offenders)
    )
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_readme_honest_claims.py -q`
Expected: FAIL — `test_no_whole_product_offline_overclaim` (строка 32) и `test_badge_does_not_claim_offline` (строка 15) красные; `test_every_offline_mention_is_qualified` тоже красный на строке 32.

- [ ] **Step 3: Починить бейдж (README:15)**

Заменить точную строку:

```
![Works offline · no keys](https://img.shields.io/badge/works-offline%20%C2%B7%20no%20keys-success)
```

на:

```
![no extra keys · no extra cost](https://img.shields.io/badge/no%20extra%20keys%20%C2%B7%20no%20extra%20cost-success)
```

- [ ] **Step 4: Починить строку блока «Что это» (README:32)**

Заменить точную подстроку:

```
инструмент решений, не ролевая игра и не генератор афоризмов. Работает офлайн, без ключей и оплаты.
```

на:

```
инструмент решений, не ролевая игра и не генератор афоризмов. Не требует своих ключей и оплаты —
работает на агенте, который у тебя уже есть; сам контур честности не нуждается в сети. Полный
офлайн — только на локальных моделях.
```

- [ ] **Step 5: Прогнать гард — зелёный**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_readme_honest_claims.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Проверить selfdoc-гард (новый тест-файл мог сдвинуть счётчик)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_fresh.py -q`
- Если PASS — regen не нужен, перейти к Step 8.
- Если FAIL (индекс считает тест-файлы, их стало больше) — Step 7.

- [ ] **Step 7: Регенерировать selfdoc (только если Step 6 упал)**

```bash
python3 scripts/gen_selfdoc.py
python3 scripts/build_manual.py
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_selfdoc_fresh.py -q
```
Expected: PASS после regen.

- [ ] **Step 8: Коммит**

```bash
git add tests/test_readme_honest_claims.py README.md
git add docs/selfdoc/index.json docs/MANUAL.md 2>/dev/null || true
git commit -m "fix(readme): честный офлайн-клейм (контур офлайн, рассуждение на хосте) + регресс-гард"
```

---

### Task 2: Citation-transparency на витрину (⚠ позиционное — утром пройтись голосом)

**Files:**
- Modify: `README.md` — герой (после слогана, ~строки 7-11) + секция «Почему этому можно верить» (~64-76)

- [ ] **Step 1: Добавить проверяемую строку-пруф в героя**

В блоке героя (внутри `<div align="center">`, сразу ПОСЛЕ абзаца
«Спорят с тобой и между собой. И **не выдумывают цитаты** — это вшито в основу.» и ПЕРЕД строкой
бейджей `[![CI]...`) вставить новый абзац:

```
Каждая 🔵-цитата сверена с подлинным текстом автора **посимвольно**; чего в корпусе нет —
советник **не произносит**. Это можно проверить, а не поверить на слово.
```

- [ ] **Step 2: Переупорядочить «Почему этому можно верить» — citation-proof первым**

В секции «## Почему этому можно верить» сейчас порядок: вводная → таблица маркеров → абзац
«Плюс анти-лесть…». Оставить таблицу и абзац анти-лести как есть, но ПЕРЕД таблицей (сразу после
строки «Это не «чат-бот в роли мудреца». Каждое слово помечено **защитным контуром**:») вставить
абзац-пруф, выносящий верифицируемость вперёд:

```
Главный пруф — не в тоне, а в проверяемости: **дословная цитата (🔵) сверяется с подлинным
корпусом автора кодом, посимвольно**, и несёт источник. Не нашлось точной строки — советник
честно молчит (fail-closed), а не сочиняет. Это то, что отличает инструмент решений от
«отыграй мудреца»: заявление можно перепроверить.
```

- [ ] **Step 3: Прогнать гард — остаётся зелёным**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_readme_honest_claims.py -q`
Expected: PASS (новые абзацы не содержат слова «офлайн»).

- [ ] **Step 4: Коммит**

```bash
git add README.md
git commit -m "docs(readme): citation-transparency на витрину — проверяемая цитата как заголовочный пруф"
```

---

### Task 3: Боль-хук как предложение (⚠ вкусовое — НЕ финал, выбор голоса за юзером)

**Files:**
- Modify: `README.md` — герой (внутри `<div align="center">`, рядом со слоганом)

- [ ] **Step 1: Вставить HTML-комментарий-предложение боль-хука**

Сразу ПОСЛЕ строки заголовка `# Consilium Principis` и ПЕРЕД слоганом
«**Личный совет директоров из великих умов — для твоих решений.**» вставить HTML-комментарий
(в рендере невидим, юзер выберет голос утром):

```
<!-- ⚠ вариант боль-хука на утро (Ole Lehmann: вести болью, не механикой) — выбери голос сам:
     "Один ИИ поддакивает и выдаёт обтекаемое среднее. Совет из разных линз — спорит, расходится
      и ловит то, что ты пропустил." Поставить строкой над/под слоган или выкинуть. -->
```

- [ ] **Step 2: Прогнать гард — зелёный**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_readme_honest_claims.py -q`
Expected: PASS.

- [ ] **Step 3: Коммит**

```bash
git add README.md
git commit -m "docs(readme): боль-хук как предложение-коммент (голос выбирает юзер)"
```

---

## Финал (контроллер, НЕ субагент)

- [ ] Полный офлайн-сьют: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` — зелёный (env-flaky `test_ssrf_check_passes_public_blocks_private` игнорировать).
- [ ] Финальное whole-feature ревью (спека↔диф).
- [ ] Оставить на ветке `feat/moat-legible`. **НЕ push, НЕ merge.** Отчёт для догфуда.

## Self-Review (контроллер)

**Spec coverage:** §1 честный офлайн → Task 1. §2 citation на витрину → Task 2. §3 боль-хук → Task 3.
§4 регресс-гард → Task 1. selfdoc-regen → Task 1 Step 6-7. Пробелов нет.
**Placeholder scan:** конкретный код/строки везде; ⚠-пометки — намеренные флаги вкусовых решений, не плейсхолдеры.
**Consistency:** имя файла-гарда `tests/test_readme_honest_claims.py` и QUALIFIERS едины во всех задачах;
строка 32-после-правки содержит «локальн» → проходит `test_every_offline_mention_is_qualified`.
