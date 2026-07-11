# Moat-Fit 3 Tools — Design Spec

**Дата:** 2026-07-11 · **Ветка:** `feat/moat-legible` · **Статус:** апрув получен (Илья: «ок»).

Реализация фич C/D из [[features-moat-fit]] + новый proof-card. Юзер выбрал набор
Session-share + Proof-card + Daily-ritual (именованные режимы почти целиком уже есть → только
триггеры-синонимы). Все три — поверх существующего ДЕТЕРМИНИРОВАННОГО гейта 🔵, контур не ослабляем.

## Открытие при исследовании кода (сузило скоуп)

- `session_render.render_html(s)` / `render_md(s)` УЖЕ отдают самодостаточный, экранированный
  (`html.escape`), без-`<script>` shareable-артефакт заседания: вопрос → советники → 🔵-цитаты с
  источником → «где расходятся» → синтез → шаг → легенда 🔵/🟡. Тул `render_session` их уже
  экспонирует (`surface=md|html|widget`). → **Session-share НЕ строит рендер с нуля**, а
  добавляет то, чего нет: панель абстеншенов + share-футер, обёрнутые в отдельный entry-point.
- `_fidelity_check(quote, advisor_dir)` → `{status, verbatim, source}` (детерминированный,
  офлайн) — основа proof-card и quote-of-day.
- `_cite(advisor_dir, query, ...)` → верифицированные quote-объекты; корпус читается из
  `advisor_dir/build/corpus.jsonl` (чанки `{text, tier, source}`).

## Инвариант приватности (жёсткий — правила безопасности + «корпуса собирает каждый сам»)

- Ни один из тулов НЕ читает `council/`, `decisions/`, `principis.md` или иные приватные журналы.
- `export_session` работает ТОЛЬКО с session-объектом, переданным host'ом (текущее заседание).
- Тулы НЕ пишут файлы на диск — возвращают СТРОКУ; host решает, сохранять ли (нет server-side
  персистенции приватных данных, нет traversal-поверхности).
- `export_session` — только по явному запросу юзера (правило 0, как save_decision_map).
- proof-card / quote-of-day работают только с PD-корпусом собранных советников → PII нет.

---

## Тул 1: `export_session` — шеримый пруф заседания

**Сигнатура:** `export_session(session, surface="md", include_abstentions=True)`
→ `{content: str, surface: str}` (строка артефакта; host сохраняет/шерит).

**Поведение:**
1. Валидирует, что `session` — dict с обязательным `question` (как render_session). Нет → отказ
   `{error}` (fail-closed, без краша).
2. Делегирует базовый рендер в `session_render.render_md(session)` (surface=md) либо
   `render_html(session)` (surface=html) — тот же canon-объект, та же атрибуция 🔵.
3. **Панель абстеншенов** (НОВОЕ, дифференциатор): если `session.abstentions` присутствует
   (список строк — темы/подвопросы, где совет пошёл в 🟡/отказ вместо фейк-цитаты), рендерит
   секцию «Что совет НЕ стал выдумывать» с этим списком. Пусто/нет ключа → секцию не рисуем
   (не выдумываем абстеншены сами — их проставляет ризонинг host'а в session-объекте).
4. **Share-футер** (НОВОЕ): атрибуция «Собрано в Consilium-Principis — совет заземлён в
   public-domain текстах, 🔵 = сверено посимвольно» + напоминание приватности «проверь перед
   тем, как делиться». Без внешних ссылок/трекеров.
5. Возвращает `{content, surface}`. Ноль записи на диск.

**Где живёт:** новая функция `export_session(session, surface, include_abstentions)` в
`session_render.py` (рядом с render_html/render_md — они уже там); handler `_export_session`
в mcp_server.py делегирует туда. Рендер абстеншенов/футера — хелперы в session_render.py
(экранирование `_e`, без `<script>` — как остальной модуль).

**Форк (решён):** формат = `md` дефолт (портируемый, безопасная вставка) + `html` (визуальный
шер). Оба уже есть в session_render.

## Тул 2: `proof_card` — карточка одной 🔵-цитаты

**Сигнатура:** `proof_card(quote, advisor_dir)` → `{content: str, verified: bool}` либо отказ.

**Поведение (fail-closed — суть рва):**
1. `_fidelity_check(quote, advisor_dir)`.
2. `verbatim == False` ИЛИ `status != "🔵"` → **карточки НЕТ**: `{verified: False, content: None,
   note: "не сверено посимвольно — карточку не рисую"}`. (🟢-комментарий тоже не пускаем на
   пруф-карту 🔵 — карточка заявляет первоисточник.)
3. verbatim 🔵 → самодостаточный html: цитата крупно + источник (`fc["source"]`) + бейдж
   «🔵 сверено посимвольно с источником». Экранирование, без `<script>`, `color-scheme:light dark`
   (как session_render). PII нет.

**Где живёт:** функция `render_proof_card(quote, source)` в session_render.py; handler
`_proof_card` в mcp_server.py (вызывает `_fidelity_check`, при 🔵 → render_proof_card).

## Тул 3: `quote_of_day` — verbatim-цитата дня (pull-only)

**Сигнатура:** `quote_of_day(advisor_dir=None, date=None)`
→ `{text, source, advisor, marker: "🔵"}` либо `{note}` если пул пуст.

**Поведение:**
1. `advisor_dir` не задан → берёт первого собранного советника из доски (как board_status
   перечисляет; если ни одного — `{note: "нет собранных советников"}`).
2. Читает `advisor_dir/build/corpus.jsonl`, фильтрует чанки тира P1/P2 (первоисточник → 🔵).
   Пул пуст → `{note}`.
3. **Детерминированный выбор по дате:** `idx = hash_stable(date_str) % len(pool)`, где `date_str`
   = переданный `date` или сегодня (`datetime.date.today().isoformat()`). Стабильно в течение дня;
   `date` — инъекция для тестов (детерминизм). `hash_stable` — свой (не встроенный `hash`, он
   рандомизирован PYTHONHASHSEED): `int(hashlib.sha256(date_str.encode()).hexdigest()[:8], 16)`.
4. Прогоняет выбранный чанк через `_fidelity_check` (гарантия 🔵; если вдруг не 🔵 — берёт
   следующий по пулу, до N попыток; все не-🔵 → `{note}`). Возвращает `{text, source, advisor,
   marker}`.

**Где живёт:** handler `_quote_of_day` в mcp_server.py. Чтение корпуса — тем же способом, что
существующий код читает `build/corpus.jsonl` (искать хелпер; если нет — локальный jsonl-ридер).
**Pull-only:** никакого пуша/крона — только по вызову (по запросу юзера через рецепт).

---

## Рецепты (data-level, discoverable) + именованные режимы

В `recipes.json` (+ гард в tests/test_recipes.py):
- `share-session` — триггеры «поделись заседанием / экспортируй совет / сохрани как пруф» →
  ведёт host к export_session.
- `quote-of-day` — «цитата дня / мысль дня / вдохнови» → quote_of_day.
- `proof-card` — «покажи пруф цитаты / карточка цитаты / докажи цитату» → proof_card.
- **Именованные режимы:** НЕ плодим тул — добавляем синонимы-триггеры «debate / дебаты /
  панель экспертов / expert panel» в существующие `clash-two` (debate) и `full-council` (panel).

## Регистрация тулов

Три записи в `TOOLS`-словаре mcp_server.py (как cite/render_session): description (host видит
через initialize; Rule 1 «тихая оркестрация» — описание техничное, host сам ведёт простым языком),
input_schema, handler. Минимальная строка в INSTRUCTIONS НЕ обязательна — рецепты + tool-registry
достаточны; если добавляем, то additive, контур не трогаем.

## Testing (TDD, офлайн)

Офлайн-CI: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`.

- **export_session** (`tests/test_export_session.py`): валидный session → md/html содержит вопрос,
  синтез, 🔵-цитаты с источником; `abstentions` присутствует → секция «Что совет НЕ стал
  выдумывать» есть; нет ключа → секции нет; футер-атрибуция присутствует; нет `<script>`; невалидный
  session (без question) → `{error}` без краша; НЕ читает файлов (unit, только объект).
- **proof_card** (`tests/test_proof_card.py`): 🔵-цитата (fixture-корпус tier P1, паттерн
  test_fidelity_tiers.py) → `verified True`, html с источником + бейдж, без `<script>`; НЕ-verbatim
  → `verified False`, content None; 🟢-цитата (S-тир) → отказ (не пускаем на 🔵-карту).
- **quote_of_day** (`tests/test_quote_of_day.py`): fixture-корпус P1/P2 → `{text, source, advisor,
  marker:"🔵"}`; тот же `date` → тот же чанк (детерминизм); разные `date` → выбор варьируется;
  пустой/не-P1 пул → `{note}` без 🔵; выбранный текст РЕАЛЬНО есть в корпусе (не выдуман).
- **recipes** (расширить tests/test_recipes.py): три новых рецепта присутствуют/валидны;
  `match_recipe` находит share-session/quote-of-day/proof-card; debate-синоним → clash-two.
- selfdoc-regen при новых тест-файлах (`gen_selfdoc.py` + `build_manual.py`, коммит обоих).

## Out of scope

- Кроновый пуш цитаты дня (только pull).
- Server-side сохранение артефактов (возвращаем строку, host сохраняет).
- Автоэкспорт `council/` / реальных решений (инвариант приватности).
- og:image генерация картинкой (proof_card отдаёт html; картинку делает юзер из html — как demo-GIF).
- Новый тул под именованные режимы (переиспользуем clash-two/full-council).

Связано: [[features-moat-fit]], [[moat-legible-branch]], [[competitor-demo-scenarios]],
[[council-topology-northstar]].
