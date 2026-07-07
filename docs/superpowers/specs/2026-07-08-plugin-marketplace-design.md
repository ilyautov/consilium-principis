# Consilium-Principis как Claude Code плагин + self-marketplace (Дизайн A) — spec

**Дата:** 2026-07-08
**Статус:** одобрен (Approach A — MCP несёт вес, тонкий skill-консьерж; обогащён ролью «помощник установки/онбординга»)
**Область:** упаковать репозиторий в устанавливаемый Claude Code плагин, раздаваемый через self-hosted marketplace, **не сломав** существующий standalone-путь `install.py`. Плюс понятность доставки (README — один золотой путь).

## Зачем

Сейчас единственный способ доставки — «дай Claude ссылку, он прогонит `install.py`». Нативный современный канал находимости — Claude Code **plugin marketplace**: `/plugin marketplace add ilyautov/consilium-principis` → `/plugin install consilium-principis@<marketplace>`. Референс — `JuliusBrussee/caveman` (многоканальная доставка). Для *скилла* правильный канал — marketplace, не PyPI (PyPI — отложенный трек для MCP-сервера как пакета).

## Ключевой факт, на котором стоит вся архитектура

`scripts/mcp_server.py` уже отдаёт хосту **полные INSTRUCTIONS (16.7KB, ~4200 токенов)** через штатный MCP `initialize`-хендшейк (`mcp_server.py:1964`, `serverInfo.name = "consilium-principis"`, `version 0.1.0`). Значит вся хореография и правила совета доходят до хоста **по MCP-протоколу, а не через SKILL.md**. Поэтому skill в плагине не обязан тащить корневые 61KB — вес несёт MCP-сервер, а skill остаётся тонким.

## Почему НЕ переносим всё в skills/ (отвергнутый Approach B)

Корневую раскладку (`scripts/` в корне) жёстко предполагают: **91 тест-файл** (`sys.path.insert(..., "..", "scripts")`), CI (`pytest tests/`), Makefile (`scripts/moat_check.py`), selfdoc-генератор (сканирует `scripts/`+`tests/` от корня), 18 ссылок в корневом SKILL.md. Перенос всего в `skills/consilium-principis/` задел бы всё это — высокий риск ради того, что MCP уже решает (отдаёт INSTRUCTIONS). YAGNI.

## Архитектура (Approach A)

### Раскладка репозитория

```
consilium-principis/                 ← репо = плагин = self-маркетплейс
├── .claude-plugin/
│   ├── plugin.json                  ← НОВОЕ: манифест плагина
│   └── marketplace.json             ← НОВОЕ: self-host каталог (один плагин, source ".")
├── .mcp.json                        ← НОВОЕ: MCP-сервер через ${CLAUDE_PLUGIN_ROOT}
├── skills/
│   └── consilium-principis/
│       └── SKILL.md                 ← НОВОЕ: тонкий skill-консьерж (~2-3KB)
├── SKILL.md                         ← БЕЗ ИЗМЕНЕНИЙ: полный 61KB для standalone install.py
├── scripts/ tests/ data/ lenses/ …  ← БЕЗ ИЗМЕНЕНИЙ (91 тест, CI, selfdoc целы)
├── mcp.json / mcp.example.json      ← ПРАВКА: убрать хардкод-абсолют, дать плагин/${CLAUDE_PLUGIN_ROOT} вариант
├── README.md                        ← ПРАВКА: /plugin как золотой путь №1
├── install.py                       ← БЕЗ ИЗМЕНЕНИЙ
└── pyproject.toml / LICENSE / …
```

### Компоненты

**`.claude-plugin/plugin.json`** — манифест. Обязательно `name` (kebab-case, `consilium-principis`), `description`. Плюс `version` (`0.1.0` — синхрон с serverInfo и тегом), `author` (Ilya Autov, ilyautov@gmail.com), `homepage`/`repository` (github URL), `license` (MIT). Явная `version` → стабильные релизы (без неё каждый push = новая версия по git SHA).

**`.claude-plugin/marketplace.json`** — self-host каталог. `name` (kebab-case, напр. `consilium-marketplace`), `owner` (name Ilya Autov). `plugins: [{ name: "consilium-principis", source: ".", description, homepage, tags: ["mcp","reasoning","advisory","decision-support"] }]`. `source: "."` = плагин в корне этого же репо (self-hosting). **ВЕРИФИКАЦИЯ на этапе плана:** точный синтаксис self-host-source (`"."` vs объект `{ "source": "github", "repo": "ilyautov/consilium-principis" }`) сверить с офиц. докой `plugin-marketplaces.md` перед коммитом; если `"."` не поддержан для корня — fallback на github-source на тот же репо. **Инвариант:** `version` в plugin.json — единственный источник; в marketplace.json version НЕ дублируем (иначе неоднозначность — берётся plugin.json).

**`.mcp.json`** — объявление MCP-сервера для плагина. Ровно:
```json
{
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/mcp_server.py"]
    }
  }
}
```
`${CLAUDE_PLUGIN_ROOT}` резолвится в путь копии плагина в кэше (`~/.claude/plugins/cache/.../consilium-principis/<version>/`), где `scripts/mcp_server.py` лежит как в корне репо (ничего не переносим). Абсолютных путей нет — иначе краш в кэше. `mcp_server.py` уже location-independent (`os.path.dirname(os.path.abspath(__file__))`).

**`skills/consilium-principis/SKILL.md`** — тонкий skill-консьерж (~2-3KB), три роли, ВСЁ через существующие MCP-тулы (логику не дублирует, bash-вызовов `scripts/` НЕТ):
- **Триггер** — когда созывать: «созови совет», «спроси Аврелия», «что выгоднее — X или Y», «добавь советника/линзу».
- **Помощник установки/онбординга** — довести от `/plugin install` до первой ценности: проверить здоровье (MCP-тул doctor/board_status), собрать стартовый совет (seed_council: Аврелий+Эпиктет), подсказать FULL-тир (setup_full, опц.), «пустая доска — норма, кого посадить — решаешь ты».
- **Указатель на движок** — INSTRUCTIONS и вся механика приходят с MCP-сервера этого плагина; drive через его тулы.

**`mcp.json` / `mcp.example.json`** — сейчас `mcp.json` содержит абсолютный путь конкретной машины (`/Users/ilyautov/...`) — это машинно-специфичный артефакт в версионируемом файле. Явное решение: **нейтрализовать `mcp.json`** — заменить абсолют на тот же плейсхолдер, что в `mcp.example.json` (`python3` + `/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py`), и добавить в оба однострочную шапку-комментарий (через поле-заметку или соседний текст в CONNECT-MCP): «плагин-установка поднимает MCP сама через `.claude-plugin`/`.mcp.json`; для ручного подключения точный путь под свою машину даёт `python3 scripts/board.py mcp-config`». Так в git нет ничьего локального пути, а реальный per-machine конфиг генерится тулом.

### Поток данных (два метода, один репо, без конфликта)

- **Плагин:** `/plugin marketplace add ilyautov/consilium-principis` → `/plugin install consilium-principis@consilium-marketplace`. Claude Code клонирует репо-маркетплейс, копирует плагин (весь репо) в кэш, читает `.mcp.json` → поднимает MCP-сервер (INSTRUCTIONS приходят по `initialize`), регистрирует тонкий skill как `/consilium-principis:*`. Онбординг ведёт skill-консьерж через MCP-тулы.
- **Standalone (как сейчас):** `python3 install.py` копирует корневой `SKILL.md`+`scripts/` в `~/.claude/skills/consilium-principis/`. Не задет плагином.
- Два SKILL.md — разные механизмы (standalone-контекст vs plugin-namespace + MCP). Тонкий держим коротким и указывающим на MCP → нет дубль-дрейфа полной хореографии (она в одном месте — INSTRUCTIONS сервера).

### Обработка ошибок / подводные камни (из спеца плагинов, июль 2026)

- `${CLAUDE_PLUGIN_ROOT}` вместо абсолютов — иначе краш в кэше.
- `.claude-plugin/` строго в корне репо; манифесты — валидный JSON.
- kebab-case имена (`consilium-principis`, `consilium-marketplace`).
- `version` только в plugin.json; в marketplace.json не дублировать.
- Репо публичный (уже да). Auto-update для кастомных маркетплейсов по умолчанию off — ок.

### Тестирование

Новый оффлайн тест-гард `tests/test_plugin_manifests.py` (в CI, без сети):
1. `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json` — валидный JSON, парсятся.
2. plugin.json: `name` == `consilium-principis` (kebab), `version` присутствует и **== serverInfo version в mcp_server.py** (`0.1.0`) — единый источник, ловит рассинхрон.
3. marketplace.json: `plugins[0].name` == `consilium-principis`, `source` == `.`, **version НЕ задан** (инвариант «version только в plugin.json»).
4. `.mcp.json`: путь содержит `${CLAUDE_PLUGIN_ROOT}` и **НЕ** содержит абсолютных путей (`/Users/`, `/opt/`, `C:\`) — ловит регресс хардкода.
5. `skills/consilium-principis/SKILL.md` существует, непустой, и **не содержит вызовов `scripts/`** (инвариант «тонкий skill драйвит через MCP, не через bash») — фиксирует границу.

Существующие 1072 теста не трогаем. Весь сьют — оффлайн-инвариант (`HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=...`).

### Понятность доставки (часть B)

README: секция «Установка» переупорядочивается — **золотой путь №1 = plugin marketplace** (`/plugin marketplace add …` → `/plugin install …`), fallback — `install.py` (клик/CLI) и ручной MCP (`CONNECT-MCP.md`). Один явный вход, остальное — «не сработало / другой хост». Бейдж «MCP ready» уже есть; можно добавить «Claude Code plugin».

## Не-цели (эта итерация)

- Перенос `scripts/tests/data` в `skills/` (Approach B) — не делаем.
- PyPI-упаковка MCP-сервера — отложенный трек после вердикта N=1.
- npm/Gemini реестры (как у caveman) — позже, если пойдём мультиканально.
- Изменения самого MCP-сервера/контура/тулов — вне области (только упаковка + тонкий skill + README).
- hooks/agents/commands в плагине — YAGNI сейчас.

## Критерий готовности

- `/plugin marketplace add` + `/plugin install` из чистой машины поднимают MCP-сервер и регистрируют skill (проверяется вручную/докой; автоматом — гард на валидность манифестов).
- `install.py` standalone-путь работает как раньше (1072 зелёных, ничего не переносили).
- Гард манифестов зелёный в оффлайн-CI; версии синхронны; ноль абсолютных путей в `.mcp.json`.
- README даёт один золотой путь установки.
