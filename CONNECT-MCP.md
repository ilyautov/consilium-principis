# Подключение Consilium как MCP-сервера

Два способа пользоваться Consilium — выбери под свой хост (можно оба, один репозиторий):

| Хост | Способ | Что получаешь |
|---|---|---|
| **Claude Code** | навык (`python3 install.py`) | хост сам гоняет скрипты; скажи «с чего начать» |
| **Cowork / Claude Desktop / любой MCP-хост** | MCP-сервер (ниже) | весь цикл как тулы — **не выходя из агента** |

Через MCP доступен **полный жизненный цикл без терминала**: `doctor` (готовность машины),
`seed_council` (стартовый совет), `build_advisor` (советник под ключ), `ingest_telegram`
(корпус Принцепса), `setup_full` (FULL-тир), `render_session`/`list_recipes` (виджеты для Cowork),
плюс контур-тулы (`fidelity_check`/`retrieve`/…). Всего 24 тула.

## Шаг 0 — репозиторий на машине (единственный внешний шаг)

```bash
git clone https://github.com/ilyautov/consilium-principis ~/consilium-principis
```
Это chicken-egg: сам MCP-сервер нельзя подключить им же. Дальше — всё внутри агентов.
**Важно:** Cowork/Code должны жить на **этой же машине** — тогда личный корпус Принцепса
остаётся локально (инвариант рва), а сборка идёт как обычно.

## Самое простое — одной командой (Claude Desktop / Cowork)

Скрипт сам впишет сервер в `claude_desktop_config.json`, **сохранив соседние серверы**, с бэкапом:
```bash
python3 ~/consilium-principis/scripts/board.py mcp-install --dry-run   # показать, что изменится
python3 ~/consilium-principis/scripts/board.py mcp-install             # применить (+бэкап)
```
Затем **полностью перезапусти Claude Desktop**. Путь к серверу и интерпретатор подставляются
автоматически (от `__file__`). Свой путь к конфигу — `--config <файл>`. Ниже — ручной вариант и
`claude mcp add` для Claude Code.

## Шаг 1 (ручной вариант) — получить готовый конфиг (путь подставится сам)

```bash
python3 ~/consilium-principis/scripts/board.py mcp-config        # гайд под все хосты
python3 ~/consilium-principis/scripts/board.py mcp-config --json # только JSON-сниппет
```

Сниппет имеет вид (см. `mcp.example.json`):
```json
{ "mcpServers": { "consilium-principis": {
    "command": "python3",
    "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
} } }
```

## Шаг 2 — зарегистрировать сервер в хосте

- **Claude Code (CLI):**
  ```bash
  claude mcp add consilium-principis -- python3 ~/consilium-principis/scripts/mcp_server.py
  ```
- **Claude Desktop И Cowork — один конфиг.** Для локального stdio-сервера это файл, не UI
  (UI в Desktop — про `.mcpb`-бандлы и удалённые HTTP-коннекторы). macOS:
  ```
  ~/Library/Application Support/Claude/claude_desktop_config.json
  ```
  Добавь ключ внутрь существующего `mcpServers` (рядом с другими серверами, не替ируя блок).
  **Механизм:** Claude Desktop спавнит локальные stdio-серверы у себя и **бриджит их в песочницу
  Cowork** — поэтому один и тот же конфиг включает тулы и в Desktop, и в Cowork. Тулы появятся как
  `mcp__consilium-principis__doctor`, `…__seed_council` и т.д.
- **Рестарт после правок.** Hot-reload у stdio нет: изменил конфиг ИЛИ код сервера → полностью
  выйди из Claude Desktop и открой заново (после старта серверу пара секунд на «подключается»).
- **cwd при спавне не определён — уже учтено.** Сервер резолвит все пути от `__file__` (корня
  репо), а не от cwd; относительный `advisor_dir` («advisors/x») находится независимо от того,
  откуда Desktop запустил процесс. Без этого контур молча ушёл бы в 🟡.

> Сохранять личный конфиг можно как `mcp.json` в корне репо — он в `.gitignore`
> (содержит абсолютный путь машины). В репозиторий едет только `mcp.example.json`.

## Шаг 3 — проверить и начать

В агенте вызови тул **`doctor`** — покажет Python, доступный тир (есть ли ollama), и самотест
рва (реальный P1-фрагмент → 🔵, фейк → None). Затем **`seed_council`** — соберёт стартовый
совет (Марк Аврелий + Эпиктет, public-domain).

## Безопасность: граница — в коде сервера

Подключённый MCP-сервер исполняется **нативно на машине** (как дочерний процесс Claude Desktop),
**вне** песочницы Cowork. Значит у него полный доступ к файловой системе и сети под твоим юзером —
ровно то, что нужно для сборки корпусов и фетча public-domain. Песочница ограничивает только
собственный bash агента, не твой сервер. Поэтому **легальную/безопасную границу держи в самом
сервере**: фетч — только public-domain, запись — только в `advisors/*/sources/` и
`principis_corpus/`, как уже сделано (см. правила в SKILL.md). Доступ широкий — дисциплину задаёт код.

## Зависимости

- **Python 3.10+** — обязательно.
- **SIMPLE-тир** (лексический поиск + контур) работает на голом Python, без pip-установок.
- **FULL-тир** (семантика) — опционально `ollama` + `bge-m3`; подними тулом `setup_full`
  (системный `ollama` он не ставит молча — вернёт инструкцию под твою ОС). Без него — мягкая
  деградация до SIMPLE; **контур честен на любом тире**.
