# Подключение Consilium как MCP-сервера

Два способа пользоваться Consilium, выбери под свой хост (можно оба, один репозиторий):

| Хост | Способ | Что получаешь |
|---|---|---|
| **Claude Code** | навык (`python3 install.py`) | хост сам гоняет скрипты; скажи «с чего начать» |
| **Claude Desktop / другой MCP-хост** | MCP-сервер (ниже) | MCP-интерфейс; совместимость зависит от хоста |

MCP-сервер предоставляет интерфейс жизненного цикла: `doctor` (готовность машины),
`seed_council` (стартовый совет), `build_advisor` (советник под ключ), `ingest_telegram`
(корпус Принцепса), `setup_full` (FULL-тир), `render_session`/`list_recipes` (виджеты для Cowork),
контур-тулы (`fidelity_check`/`cite`/`gate_verdict`/`retrieve`, двухфазный судья-гейт цитат),
decision-calc (`validate_decision_map`/`run_calculation`/`save_decision_map`, то есть 📐 карта решения и
Монте-Карло), петля исхода (`loop_status`/`pending_outcomes`/`advisor_weights`), сборка из
общественного достояния (`catalog_list`/`catalog_search`/`catalog_preview`/`catalog_add`), ситуационная
карта (`capture_situation`/`situation_analyze`/`situation_stress_test`), выходы заседания
(`decision_record`/`proof_card`/`quote_of_day`/`export_session`), само-документация (`explain_self`)
плюс тулы линз и жизненного цикла (`build_lens`/`add_source`/`config_*`/`ollama_*`). Состав MCP-интерфейса развивается; смотри живой список через `tools/list` или `explain_self`. Проверенный статус отдельных хостов — в [`docs/CONNECT-HOSTS.md`](docs/CONNECT-HOSTS.md).

## Подключение за 3 шага (Claude Desktop / Cowork)

> Не нужен ни программистский опыт, ни знание терминов, всего три коротких шага.

### Шаг 0. Положить файлы на машину (единственный «технический» шаг)

Нужна папка с проектом на **той же машине**, где стоит Claude Desktop/Cowork: так твой личный
корпус остаётся локально (это и есть гарантия приватности). Любой из двух способов:

- **Без терминала:** скачай **ZIP** проекта и распакуй в домашнюю папку (получится
  `~/consilium-principis`) → [скачать ZIP](https://github.com/ilyautov/consilium-principis/archive/refs/heads/master.zip)
- **С терминалом (git):**
  ```bash
  git clone https://github.com/ilyautov/consilium-principis ~/consilium-principis
  ```

Это «курица-яйцо»: сам MCP-сервер нельзя подключить им же, поэтому один раз файлы кладём руками.
Дальше всё происходит прямо в агенте.

### Шаг 1. Подключить одной строкой

Проще всего **отдать эту строку самому Claude** (в Cowork/Code на той же машине) и попросить
выполнить; либо вставь её в терминал сам:
```bash
python3 ~/consilium-principis/scripts/board.py mcp-install
```

На Windows используй вместо этой строки:

```powershell
py -3 ~/consilium-principis/scripts/board.py mcp-install
```

Если `py` отсутствует, сначала проверь, что `python` — настоящий Python 3.10+
(`python -c "import sys; assert sys.version_info >= (3, 10)"`), затем замени `py -3` на `python`.
Не используй Store-alias `python3`.

Скрипт сам впишет сервер в конфиг Claude Desktop, **сохранив соседние серверы**, сделает бэкап и
подставит пути. Хочешь сперва увидеть, что изменится, добавь в конец `--dry-run`.
Затем **полностью перезапусти Claude Desktop** (у локальных серверов нет горячей перезагрузки).

### Шаг 2. Начать (просто словами)

Открой агент и напиши «**с чего начать**». Совет сам проверит готовность и поведёт за руку,
никаких команд знать не нужно, говори обычным языком. (Под капотом это проверка здоровья и сборка
стартового совета, Марк Аврелий и Эпиктет, public-domain, но тебе об этом думать не надо.)

<details>
<summary>⚙️ Технические детали: ручной конфиг, <code>claude mcp add</code>, как сервер спавнится</summary>

**Готовый конфиг-сниппет** (путь подставится сам):
```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config        # гайд под все хосты
python3 scripts/board.py mcp-config --json # только JSON-сниппет
```
На Windows:
```powershell
py -3 scripts/board.py mcp-config --json
```
Вид сниппета (см. `mcp.example.json`):
```json
{ "mcpServers": { "consilium-principis": {
    "command": "python3",
    "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
} } }
```

**Регистрация вручную:**
- **Claude Code (CLI):**
  ```bash
  claude mcp add consilium-principis -- python3 ~/consilium-principis/scripts/mcp_server.py
  ```
- **Claude Desktop, конфиг в файле** (не UI; UI в Desktop про `.mcpb`-бандлы и удалённые
  HTTP-коннекторы). macOS:
  ```
  ~/Library/Application Support/Claude/claude_desktop_config.json
  ```
  Добавь ключ внутрь существующего `mcpServers` (рядом с другими серверами, не заменяя блок).
  Это документированный путь для Claude Desktop. Интеграция с Cowork отдельно не smoke-tested;
  не считай этот конфиг подтверждением поддержки Cowork.
- **Рестарт после правок.** Hot-reload у stdio нет: изменил конфиг ИЛИ код, полностью выйди из
  Claude Desktop и открой заново.
- **cwd при спавне не определён, уже учтено.** Сервер резолвит пути от `__file__` (корня репо),
  не от cwd; относительный `advisor_dir` находится независимо от места запуска. Без этого контур
  молча ушёл бы в 🟡.
- Личный конфиг можно хранить как `mcp.json` в корне репо, он в `.gitignore` (абсолютный путь
  машины). В репозиторий едет только `mcp.example.json`.
- Хочешь проверить здоровье явно, зови тул **`doctor`** (Python, тир, самотест рва: P1-фрагмент → 🔵,
  фейк → None); стартовый совет вручную через **`seed_council`**.
- **Windows:** для ручного `mcp-install` и генератора используй `py -3` по инструкции выше; полный
  разбор и fallback лежат в [`docs/CONNECT-HOSTS.md`](docs/CONNECT-HOSTS.md#Windows-используй-сгенерированный-конфиг).

</details>

## Безопасность: граница в коде сервера

Подключённый MCP-сервер исполняется **нативно на машине** (как дочерний процесс Claude Desktop),
**вне** песочницы Cowork. Значит у него полный доступ к файловой системе и сети под твоим юзером,
ровно то, что нужно для сборки корпусов и фетча public-domain. Песочница ограничивает только
собственный bash агента, не твой сервер. Поэтому **легальную и безопасную границу держи в самом
сервере**: фетч только public-domain, запись только в `advisors/*/sources/` и
`principis_corpus/`, как уже сделано (см. правила в SKILL.md). Доступ широкий, дисциплину задаёт код.

## Зависимости

- **Python 3.10+**, обязательно.
- **SIMPLE-тир** (лексический поиск + контур) работает на голом Python, без pip-установок.
- **FULL-тир** (семантика) опционально: `ollama` + `bge-m3`; подними тулом `setup_full`
  (системный `ollama` он не ставит молча, вернёт инструкцию под твою ОС). Без него мягкая
  деградация до SIMPLE; **контур честен на любом тире**.
- **Hybrid**-ретрив доступен только по opt-in; это не отдельный тир поддержки.
