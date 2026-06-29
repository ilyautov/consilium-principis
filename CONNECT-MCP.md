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

## Шаг 1 — получить готовый конфиг (путь подставится сам)

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
- **Claude Desktop:** вставь JSON-сниппет в `claude_desktop_config.json` (раздел `mcpServers`),
  перезапусти приложение.
- **Cowork:** зарегистрируй stdio-сервер с тем же `command` + `args`. Точный UI/место —
  в интерфейсе Cowork (формат конфига стандартный, как выше).

> Сохранять личный конфиг можно как `mcp.json` в корне репо — он в `.gitignore`
> (содержит абсолютный путь машины). В репозиторий едет только `mcp.example.json`.

## Шаг 3 — проверить и начать

В агенте вызови тул **`doctor`** — покажет Python, доступный тир (есть ли ollama), и самотест
рва (реальный P1-фрагмент → 🔵, фейк → None). Затем **`seed_council`** — соберёт стартовый
совет (Марк Аврелий + Эпиктет, public-domain).

## Зависимости

- **Python 3.10+** — обязательно.
- **SIMPLE-тир** (лексический поиск + контур) работает на голом Python, без pip-установок.
- **FULL-тир** (семантика) — опционально `ollama` + `bge-m3`; подними тулом `setup_full`
  (системный `ollama` он не ставит молча — вернёт инструкцию под твою ОС). Без него — мягкая
  деградация до SIMPLE; **контур честен на любом тире**.
