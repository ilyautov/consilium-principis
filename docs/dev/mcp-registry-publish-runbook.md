# MCP Registry — runbook публикации (до кнопки)

Статус на 2026-07-14: листинг подготовлен, **не опубликован**. Кнопки (сборка
артефакта, GitHub Release, OAuth-логин, publish, флип репо в public) — за Ильёй.
Здесь — что уже в репо, что нажать и в каком порядке, и один открытый вопрос,
который надо снять ПЕРЕД `mcp-publisher publish`.

Реестр (`registry.modelcontextprotocol.io`) в **preview** — возможны data-resets и
слом схемы. Сверять с `modelcontextprotocol.io/registry/quickstart` перед подачей.

---

## Что решено

- **Формат артефакта — `mcpb`** (self-contained бандл, ассет GitHub Release).
  Почему не PyPI: pyproject.toml сознательно НЕ пакет (`[build-system]` убран);
  mcpb не требует внешнего пакет-реестра и не разворачивает это решение. Родной
  Anthropic-формат — согласуется с уже смерженной plugin-marketplace-дистрибуцией.
- **Namespace** — `io.github.ilyautov/consilium-principis` (GitHub-OAuth
  подтверждает владение неймспейсом `io.github.ilyautov/*`).
- **Пруф владения mcpb** — НЕ строка в README (это для pypi/nuget). Для mcpb:
  URL артефакта обязан содержать «mcp» (даёт расширение `.mcpb`) + `fileSha256`.

## Что уже в репо (подготовлено)

| Файл | Роль |
|---|---|
| `server.json` | манифест реестра: name/namespace, repository, `packages[].registryType=mcpb`, identifier=URL релиза, `fileSha256` (плейсхолдер), transport stdio |
| `manifest.json` | mcpb-манифест бандла: `manifest_version 0.3`, `server.type=python`, entry_point `scripts/mcp_server.py`, `command python3`, args через `${__dirname}` |
| `tests/test_plugin_manifests.py` | гарды: синхрон версий (pyproject/plugin.json/serverInfo/manifest.json/server.json = 0.1.0), namespace-паттерн, mcpb-URL содержит `.mcpb`, transport stdio, sha256-плейсхолдер помечен как «залить перед публикацией» |

`fileSha256` намеренно = `REPLACE-WITH-sha256-AT-RELEASE-TIME` — сентинел, а не
64-нулевой фейк: если случайно запустить publish с плейсхолдером, валидатор
споткнётся громко, а не пропустит подделку.

---

## ⚠ Открытый вопрос — снять ДО publish

**Корпус в бандле.** `advisors/*/corpus.jsonl` в `.gitignore` (каждый собирает
корпус сам). Значит `mcpb pack` из репо кладёт код + указатели советников + PD-сиды,
но **ноль готового корпуса**. Из коробки бандл будет честно fail-closed воздерживаться
на всём, пока пользователь не соберёт корпус в распакованной хостом директории.

Развилки перед кнопкой (выбрать одну):
1. **Принять fail-closed из коробки** — бандл ставится, при первом запросе воздержание +
   подсказка «собери корпус: …». Честно по духу рва, но «пустой» первый прогон.
2. **Пред-собрать 3 PD-сида** (Marcus Aurelius и др. из Gutenberg) и вложить их
   `corpus.jsonl` в бандл как исключение из gitignore ТОЛЬКО внутри `.mcpb` (не в git).
   Даёт рабочее демо из коробки на public-domain материале. Больше сборочной работы.
3. **Отложить mcpb, листить позже** — если распакованная хостом директория окажется
   read-only и corpus-build туда не встанет.

Проверить перед выбором: пишет ли хост распакованный бандл в writable-директорию,
и куда `scripts/corpusbuild` кладёт `corpus.jsonl` относительно `${__dirname}`.

---

## Кнопки (по порядку)

### 1. Собрать бандл
```bash
npm install -g @anthropic-ai/mcpb        # или npx @anthropic-ai/mcpb ...
cd <repo>
mcpb pack                                 # читает manifest.json → consilium-principis.mcpb
```
Проверить размер и содержимое: в бандл НЕ должны попасть `tests/`, `assets/*.gif`,
`docs/`, `.github/`, `_archive/`. Если mcpb поддерживает `.mcpbignore` — исключить их;
иначе паковать из подготовленной стейджинг-директории.

### 2b. Гард содержимого бандла (ОБЯЗАТЕЛЬНО до Release)
```bash
unzip -Z1 consilium-principis.mcpb | python3 scripts/ci_bundle_guard.py -
# ожидается: bundle-guard: OK. Любой forbidden путь → СТОП, не публиковать.
```

### 2. Посчитать и вписать sha256
```bash
openssl dgst -sha256 consilium-principis.mcpb
```
Вставить хеш в `server.json` → `packages[0].fileSha256` (заменить сентинел).

### 3. GitHub Release
Создать релиз `v0.1.0`, приложить `consilium-principis.mcpb` ассетом. Убедиться, что
URL скачивания **точно совпадает** с `identifier` в `server.json`:
`https://github.com/ilyautov/consilium-principis/releases/download/v0.1.0/consilium-principis.mcpb`
(Предусловие: репо уже public.)

### 4. Установить mcp-publisher
```bash
# macOS/Linux
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/
# или: brew install mcp-publisher
```

### 5. Логин (GitHub device-OAuth)
```bash
mcp-publisher login github
```
Открыть ссылку, ввести код, авторизовать. Namespace `io.github.ilyautov/*`
подтверждается этим логином.

### 6. Публикация
```bash
cd <repo>          # директория, где лежит server.json
mcp-publisher publish
```
Ожидаемо: `✓ Successfully published` + `io.github.ilyautov/consilium-principis 0.1.0`.

### 7. Проверка
```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.ilyautov/consilium-principis"
```
Должен вернуть наш server-метаданные.

---

## Даунстрим-каталоги (ручная подача после реестра)

- **PulseMCP** — авто-ингестит из официального реестра / GitHub, обычно без ручной подачи.
- **Smithery** (`smithery.ai`) — ручная подача, требует репо + описание.
- **Glama** (`glama.ai/mcp`) — ручная / авто по GitHub-топикам.
- **MCP.so** — ручная подача формой.

Отдельно от реестра уже работает **Claude Code plugin marketplace**:
`/plugin marketplace add ilyautov/consilium-principis` →
`/plugin install consilium-principis@consilium-marketplace` (смержено, master d8beb77).

---

## Предусловия-кнопки Ильи (необратимое / аккаунты)

- Репо `ilyautov/consilium-principis` флипнут в **public** (URL релиза/repository должны резолвиться).
- Ротация OPENROUTER-ключа — не связана с публикацией реестра (ключ только для
  опциональных экспериментов/сильной федерации, в core-сервере не нужен, в `server.json`
  env-переменных НЕТ).
