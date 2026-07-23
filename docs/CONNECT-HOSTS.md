[English](CONNECT-HOSTS.en.md) · **Русский**

# Подключение к разным хостам (не только Claude Code)

> Релиз: [v0.1.1](https://github.com/ilyautov/consilium-principis/releases/download/v0.1.1/consilium-principis.mcpb)

Ключевой факт архитектуры: логика советников, контура верности, гейта цитат и 📐 карты
решения живёт в **MCP-сервере**, то есть в `scripts/mcp_server.py`. Он отдаёт полный
`INSTRUCTIONS` из обработчика стандартного MCP-хендшейка `initialize`:

```python
if method == "initialize":
    return _rpc_result(req_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "consilium-principis", "version": "0.1.1"},
        "instructions": INSTRUCTIONS,
    })
```

Это описывает протокол, но не является обещанием совместимости каждого MCP-хоста: они по-разному
обрабатывают `instructions`, конфиг и разрешения. CI проверяет сам сервер и его stdio-протокол, но
пока не запускает настоящий Claude Code или Claude Desktop. Поэтому все host-specific рецепты ниже
экспериментальны: это отправные точки для проверки на своей машине, а не заявление о поддержке.

Общая ссылка на подробности протокола, безопасность, зависимости (Python 3.10+, SIMPLE/FULL
тир) лежит в [`CONNECT-MCP.md`](../CONNECT-MCP.md). Здесь разбор по хостам, конкретно.

## Сводная таблица

| Хост | Скилл (plugin/manual) | MCP-сервер | Проверено вживую |
|---|---|---|---|
| Claude Code | plugin (`/plugin marketplace add`) | да | ⚠ экспериментально: нет host-specific CI smoke |
| Claude Code | manual (`claude mcp add`) | да | ⚠ экспериментально: нет host-specific CI smoke |
| Claude Desktop | нет своего скилл-формата, MCP-сервер даёт весь функционал | да | ⚠ экспериментально: нет host-specific CI smoke |
| Cursor | нет | да (по документации Cursor) | ⚠ не проверено на этом хосте, подтвердите |
| Codex / OpenAI-style CLI | нет | ⚠ зависит от версии CLI, см. раздел ниже | ⚠ не проверено |
| Gemini CLI | нет | ⚠ через расширения/MCP-конфиг, см. раздел ниже | ⚠ не проверено |
| Универсальный MCP-хост | нет (нет плагин-формата вне Claude Code) | да | ⚠ зависит от хоста |

«Скилл» здесь про удобную обёртку (авто-регистрация, слэш-команда). MCP-сервер сам по
себе не требует скилл-формата: это отдельный протокол, который поддерживают многие хосты.

---

## 1. Claude Code

### Золотой путь, плагин (рекомендуется)

В Claude Code:

```
/plugin marketplace add ilyautov/consilium-principis
/plugin install consilium-principis@consilium-marketplace
```

Claude Code сам клонирует репозиторий-маркетплейс, скопирует плагин, прочитает
`.claude-plugin/plugin.json` и `.mcp.json` и поднимет MCP-сервер по описанному в нём
`command`/`args` (`${CLAUDE_PLUGIN_ROOT}/scripts/mcp_server.py`), плюс зарегистрирует тонкий
skill-слой (`/consilium-principis:*`). Подробности пакета: `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`.

После установки скажи агенту **«с чего начать»**, и сработает skill-консьерж, который сам
проверит готовность (`doctor`) и соберёт стартовый совет (`seed_council`: Марк Аврелий и
Эпиктет, public-domain).

Подробный статус фичи в `MEMORY: plugin-marketplace-shipped` (смержено в master, версии
манифестов синхронизированы гардом).

### Manual-путь (MCP напрямую, без плагина)

Если плагин не подходит (например, работаешь с локальным чекаутом репо, а не с публичным
GitHub), зарегистрируй сервер вручную:

```bash
claude mcp add consilium-principis -- python3 ~/consilium-principis/scripts/mcp_server.py
```

Или сгенерируй команду под свою машину:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

После подключения «с чего начать» так же работает (через тулы `doctor`/`seed_council`,
не через skill-обёртку: INSTRUCTIONS уже пришли по `initialize`).

---

## 2. Claude Desktop

Claude Desktop не умеет ставить Claude Code plugin-манифесты, но MCP-сервер даёт ей весь
функционал напрямую (это и есть основной сценарий, под который написан `CONNECT-MCP.md`).

Файл конфига (macOS):

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Добавь ключ **внутрь существующего** `mcpServers` (рядом с другими серверами, не заменяя
блок):

```json
{
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
    }
  }
}
```

Путь и интерпретатор подставит сам генератор:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

Либо авто-мердж скриптом (сохраняет соседние серверы, делает бэкап):

```bash
python3 ~/consilium-principis/scripts/board.py mcp-install
# --dry-run сперва покажет, что изменится
```

**Обязателен полный рестарт Claude Desktop** после правки конфига или кода сервера:
у локальных stdio-серверов нет hot-reload.

Путь Claude Desktop экспериментальный: CI проверяет конфиг-мердж и stdio MCP-сервера, но не сам
Desktop. Cowork тоже не smoke-tested отдельно: не выводи из Desktop-конфига автоматическую
поддержку Cowork и сообщи о подтверждённом запуске через [SUPPORT.md](../SUPPORT.md).

---

## 3. Cursor

⚠ Не проверено на этом хосте лично: конфигурация ниже выведена из общей MCP-поддержки
Cursor (Cursor Settings → MCP → добавление stdio-сервера через `mcp.json`), не подтверждена
на реальном запуске. Пожалуйста, подтвердите перед тем, как публиковать как «поддерживается».

Ожидаемый путь: Cursor читает конфиг MCP-серверов в формате, аналогичном
`claude_desktop_config.json` (ключ `mcpServers`, поля `command`/`args`), либо в
project-level `.cursor/mcp.json`, либо в глобальных настройках Cursor. Локальный проектный
`.mcp.json` этого репозитория (см. `mcp.example.json`, трекнутый пример; реальный `mcp.json`
в `.gitignore`) уже в нужном формате:

```json
{
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
    }
  }
}
```

Путь под свою машину подставит тот же `mcp-config`:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

После подключения попроси у Cursor-агента «с чего начать» (или явно вызови тул
`doctor`, если Cursor не выполняет INSTRUCTIONS автоматически при хендшейке; это тоже
⚠ не проверено: разные хосты по-разному используют поле `instructions` из ответа
`initialize`).

**Каверзный момент:** если Cursor не прокидывает `instructions` из `initialize` в контекст
модели (некоторые хосты просто игнорируют это поле), поведение совета не подхватится само,
тогда явно попроси агента вызвать тулы `doctor` → `seed_council` руками.

---

## 4. Codex / OpenAI-style CLI

⚠ Не проверено. Честно: поддержка MCP в Codex CLI менялась между версиями, и на момент
написания этого файла нет подтверждённого теста подключения Consilium к Codex. Если Codex
CLI в вашей версии поддерживает MCP-серверы (обычно через `~/.codex/config.toml` или
аналогичный конфиг с секцией `mcp_servers`), конфиг по смыслу тот же, команда и путь:

```toml
[mcp_servers.consilium-principis]
command = "python3"
args = ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
```

(Формат секции `[mcp_servers.<name>]` с `command`/`args` типичен для Codex CLI на момент
написания, но **не проверен на реальном запуске в рамках этого проекта**. Актуальный синтаксис
уточните в документации своей версии Codex CLI.)

Как и с Cursor, неясно (⚠ не проверено), прокидывает ли Codex поле `instructions` из
`initialize` в системный промпт модели. Если нет, попросите модель явно вызвать тул
`doctor`, затем `seed_council`, чтобы получить тот же старт, что даёт «с чего начать» в
Claude Code/Desktop.

---

## 5. Gemini CLI

⚠ Не проверено. Gemini CLI поддерживает MCP-серверы через свой конфиг расширений
(`~/.gemini/settings.json` или `.gemini/settings.json` в проекте, секция `mcpServers`,
по документации Google в целом похожа на формат Claude Desktop), но подключение Consilium
к Gemini CLI не тестировалось в рамках этого репозитория.

Ожидаемый (не подтверждённый) конфиг:

```json
{
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
    }
  }
}
```

⚠ Так же не проверено: подхватывает ли Gemini CLI `instructions` из `initialize`
автоматически, или требует явного вызова тулов. Если совет «не в курсе» своего протокола
после подключения, вызовите `doctor`, затем `seed_council` вручную.

---

## 6. Универсальный MCP-хост (любой другой)

Consilium не завязан на конкретный хост: сервер говорит по стандартному MCP (stdio,
JSON-RPC, `protocolVersion: "2024-11-05"`, `initialize` → `tools/list` → `tools/call`).
Универсальный паттерн:

```json
{
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
    }
  }
}
```

Путь под конкретную машину подставит сам скрипт, вписывать вручную не нужно:

```bash
python3 scripts/board.py mcp-config         # гайд под все хосты + JSON
python3 scripts/board.py mcp-config --json  # только JSON-сниппет
```

(Реализация в `scripts/board.py:cmd_mcp_config`, резолвит абсолютный путь к
`scripts/mcp_server.py` от `__file__`, не от `cwd`: важно, потому что разные хосты спавнят
процесс с разным/неопределённым рабочим каталогом.)

Если ваш хост поддерживает MCP, но не входит в список выше, используй сгенерированный сниппет
как основу для проверки, а не как заявление о поддержке: у каждого хоста свой формат и модель
разрешений. Не заменяй вручную путь или интерпретатор, пока сначала не попробуешь генератор.

После подключения вызовите тул `doctor` (или попросите агента), чтобы проверить
готовность машины (Python-версия, тир SIMPLE/FULL), затем `seed_council`, чтобы получить
стартовый совет (Марк Аврелий и Эпиктет).

---

## Windows: используй сгенерированный конфиг

На Windows `python3` часто отсутствует в `PATH`, поэтому не копируй вручную примеры выше с этим
именем команды. `python3 scripts/board.py mcp-config --json` подставляет **точный путь к
запущенному интерпретатору** (`sys.executable`); `mcp-install` делает то же при мердже Claude
Desktop-конфига. MCPB-бандл отдельно использует Windows Python Launcher `py -3`.

На Windows запускай генератор и авто-мердж так:

```powershell
py -3 scripts/board.py mcp-config --json
py -3 scripts/board.py mcp-install
```

Если `py` не установлен, используй `python` только после проверки, что это реальный Python 3.10+
(`python -c "import sys; assert sys.version_info >= (3, 10)"`), и замени им `py -3`. Не используй
Store-alias `python3`: он может открыть магазин вместо запуска скрипта.

Windows CI проверяет launcher, выбор конфигов и stdio `initialize`/`tools/list`, но не настоящий
запуск конкретного хоста. Поэтому этот путь экспериментальный: проверь сгенерированный конфиг в
своём хосте и сообщи о результате через [SUPPORT.md](../SUPPORT.md).

---

## Что сказать после подключения (любой хост)

Одинаково для всех: скажите агенту **«с чего начать»** (или «where do I start», по-русски
и по-английски работает через ту же логику INSTRUCTIONS). Если хост не прокидывает
`instructions` из `initialize` автоматически (см. пометки ⚠ выше по некоторым хостам),
попросите явно вызвать MCP-тулы `doctor` → `seed_council` в этом порядке: первый проверит
готовность машины (Python, тир ретрива), второй соберёт стартовый совет из public-domain
фигур (Марк Аврелий и Эпиктет), чтобы было с кем говорить сразу, без ручной настройки.
