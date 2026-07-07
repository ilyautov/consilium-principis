# Consilium как Claude Code плагин + self-marketplace (Approach A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Упаковать репозиторий в устанавливаемый Claude Code плагин, раздаваемый через self-hosted marketplace, не сломав standalone `install.py`.

**Architecture:** Approach A — MCP-сервер несёт вес (уже отдаёт INSTRUCTIONS через `initialize`), в плагин добавляем 3 машинных манифеста (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json`) + тонкий `skills/consilium-principis/SKILL.md`-консьерж. Ничего из `scripts/tests/data` НЕ переносим. Тест-гард манифестов в оффлайн-CI.

**Tech Stack:** Python stdlib (`json`, `re`, `tomllib`, `pathlib`) для гарда. JSON-манифесты. Ветка `feat/plugin-marketplace`.

---

## File Structure

- Create `.claude-plugin/plugin.json` — манифест плагина (name/version/desc/author/urls/license).
- Create `.claude-plugin/marketplace.json` — self-host каталог (один плагин, github-source на тот же репо).
- Create `.mcp.json` — объявление MCP-сервера через `${CLAUDE_PLUGIN_ROOT}`.
- Create `skills/consilium-principis/SKILL.md` — тонкий skill-консьерж (~2KB, драйвит через MCP, без bash-вызовов `scripts/`).
- Create `tests/test_plugin_manifests.py` — оффлайн-гард (валидность/синхрон версий/ноль абсолютов/граница skill).
- Modify `mcp.json` — нейтрализовать машинно-специфичный абсолютный путь.
- Modify `README.md` — `/plugin` как золотой путь установки №1.

**Инварианты (не нарушать):** ноль правок `scripts/mcp_server.py` и контура; ноль переносов `scripts/tests/data/lenses/…`; существующие 1072 теста зелёные; оффлайн-CI (`HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999`). Env-flaky `test_ssrf_check_passes_public_blocks_private` игнорируется.

---

### Task 1: Машинные манифесты плагина (plugin.json + marketplace.json + .mcp.json) + гард

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json`
- Test: `tests/test_plugin_manifests.py`

- [ ] **Step 1: Написать падающий гард** — создать `tests/test_plugin_manifests.py`:

```python
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _pyproject_version():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _serverinfo_version():
    src = (ROOT / "scripts" / "mcp_server.py").read_text(encoding="utf-8")
    m = re.search(r'"serverInfo"\s*:\s*\{[^}]*"version"\s*:\s*"([^"]+)"', src)
    assert m, "serverInfo version не найден в mcp_server.py"
    return m.group(1)


def test_plugin_manifest_valid():
    p = _load_json(".claude-plugin/plugin.json")
    assert p["name"] == "consilium-principis"
    assert re.fullmatch(r"[a-z0-9-]+", p["name"]), "name должен быть kebab-case"
    assert p["description"].strip()
    assert "version" in p


def test_marketplace_manifest_valid():
    m = _load_json(".claude-plugin/marketplace.json")
    assert re.fullmatch(r"[a-z0-9-]+", m["name"]), "marketplace name kebab-case"
    assert m["owner"]["name"].strip()
    plugins = m["plugins"]
    assert len(plugins) == 1
    entry = plugins[0]
    assert entry["name"] == "consilium-principis"
    # github-source на тот же репо (относительный "." доком не поддержан для корня)
    assert entry["source"] == {"source": "github", "repo": "ilyautov/consilium-principis"}
    assert "version" not in entry, "version только в plugin.json, не в marketplace.json"


def test_versions_in_sync():
    p = _load_json(".claude-plugin/plugin.json")
    assert p["version"] == _pyproject_version() == _serverinfo_version()


def test_mcp_json_uses_plugin_root_no_absolutes():
    raw = (ROOT / ".mcp.json").read_text(encoding="utf-8")
    m = json.loads(raw)
    srv = m["mcpServers"]["consilium-principis"]
    joined = " ".join(srv["args"])
    assert "${CLAUDE_PLUGIN_ROOT}" in joined
    assert "mcp_server.py" in joined
    assert "/Users/" not in raw and "/opt/" not in raw, "ноль абсолютных unix-путей"
    assert not re.search(r"[A-Za-z]:\\\\", raw), "ноль абсолютных windows-путей"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_plugin_manifests.py -v`
Expected: FAIL (4 теста — файлов манифестов ещё нет, `FileNotFoundError`).

- [ ] **Step 3: Создать `.claude-plugin/plugin.json`**

```json
{
  "name": "consilium-principis",
  "description": "Личный совет директоров из AI-персон реальных мыслителей, заземлённый в public-domain текстах, с защитным контуром верности (дословные цитаты, fail-closed воздержание).",
  "version": "0.1.0",
  "author": { "name": "Ilya Autov", "email": "ilyautov@gmail.com" },
  "homepage": "https://github.com/ilyautov/consilium-principis",
  "repository": "https://github.com/ilyautov/consilium-principis",
  "license": "MIT"
}
```

- [ ] **Step 4: Создать `.claude-plugin/marketplace.json`**

```json
{
  "name": "consilium-marketplace",
  "description": "Каталог Consilium-Principis — совет AI-персон с контуром верности.",
  "owner": { "name": "Ilya Autov", "email": "ilyautov@gmail.com" },
  "plugins": [
    {
      "name": "consilium-principis",
      "source": { "source": "github", "repo": "ilyautov/consilium-principis" },
      "description": "Совет AI-персон реальных мыслителей + карта решения (Монте-Карло) с fail-closed контуром верности.",
      "homepage": "https://github.com/ilyautov/consilium-principis",
      "tags": ["mcp", "reasoning", "advisory", "decision-support"]
    }
  ]
}
```

- [ ] **Step 5: Создать `.mcp.json`**

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

- [ ] **Step 6: Запустить гард — зелёный**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_plugin_manifests.py -v`
Expected: PASS (4 теста). Если `test_versions_in_sync` падает — версии plugin.json/pyproject/serverInfo разошлись; выровнять на `0.1.0` (НЕ править mcp_server.py по своей инициативе — если там не 0.1.0, СТОП и эскалация).

- [ ] **Step 7: Коммит**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json .mcp.json tests/test_plugin_manifests.py
git commit -m "feat(plugin): манифесты плагина + self-marketplace (github-source) + гард синхрона версий/ноль абсолютов"
```

---

### Task 2: Тонкий skill-консьерж

**Files:**
- Create: `skills/consilium-principis/SKILL.md`
- Test: `tests/test_plugin_manifests.py` (дописать один тест)

- [ ] **Step 1: Дописать падающий тест** — добавить в конец `tests/test_plugin_manifests.py`:

```python
def test_thin_skill_exists_no_bash_scripts():
    sk = ROOT / "skills" / "consilium-principis" / "SKILL.md"
    assert sk.exists(), "тонкий skill плагина должен существовать"
    text = sk.read_text(encoding="utf-8")
    assert text.strip()
    assert text.startswith("---"), "нужен YAML-frontmatter с description"
    # тонкий skill драйвит через MCP-тулы, НЕ через bash-вызовы scripts/ (границу фиксируем)
    assert "scripts/" not in text, "skill не должен звать локальные scripts/ — только MCP-тулы"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_plugin_manifests.py::test_thin_skill_exists_no_bash_scripts -v`
Expected: FAIL (`AssertionError: тонкий skill плагина должен существовать`).

- [ ] **Step 3: Создать `skills/consilium-principis/SKILL.md`**

```markdown
---
description: >
  Личный совет директоров из AI-персон реальных мыслителей (Сунь-цзы, Марк Аврелий, Эпиктет,
  Макиавелли и твои легальные фигуры) с защитным контуром верности. Используй когда: «созови
  совет», «спроси Аврелия», «собери совет директоров», «что выгоднее — X или Y», «добавь
  советника/линзу», «премортем», «board», «council». Движок и правила — в MCP-сервере этого
  плагина; навык подсказывает, когда созвать и как довести до первого заседания.
---

# Consilium-Principis — консьерж совета

Подключён плагин Consilium-Principis. **Движок — MCP-сервер этого плагина**: он отдаёт полные
правила (контур верности 🔵/🟢/🟡/📐, fail-closed воздержание, хореография заседания) и тулы. Этот
навык — тонкий консьерж: когда созвать совет и как быстро довести пользователя до первой ценности.
Вся работа — через MCP-тулы сервера, локальные скрипты не вызывай.

## Когда созывать
- «созови совет / собери совет директоров / что думает совет по…» → заседание-форум.
- «спроси Аврелия / что бы сказал [фигура]» → один советник, строго по его текстам.
- «что выгоднее — X или Y / стоит ли» → карта решения + Монте-Карло (📐).
- «пусть [A] и [B] поспорят», «премортем», «добавь советника/линзу», «не противоречу ли я себе».

## Довести до первой ценности (онбординг)
1. **Проверь готовность** — вызови MCP-тул состояния/здоровья (board_status / doctor): какой тир
   поиска, что настроено, один приоритетный следующий шаг.
2. **Пустая доска — это норма.** Кого посадить за стол — решает пользователь. Предложи быстрый
   старт: MCP-тул seed_council соберёт стартовый совет из public-domain мудрецов (Марк Аврелий +
   Эпиктет) за пару минут.
3. **Умный кросс-язычный поиск — опционально.** Хочет — подскажи FULL-тир (setup_full: ollama +
   bge-m3). Контур 🔵 и совет работают и без него, на лексическом полу.
4. Дальше «что умеешь?» покажет меню рецептов простыми фразами.

## Граница
Навык не качает копирайтные книги: public-domain — свободно, копирайт — только легальные копии
пользователя. Личная доска и заседания — его данные, наружу не уходят. Контур верности:
🔵 дословная цитата (проверено кодом) · 🟡 мысль в духе автора · 📐 расчёт · отказ вместо выдумки.
```

- [ ] **Step 4: Запустить — зелёный + весь файл гарда**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_plugin_manifests.py -v`
Expected: PASS (5 тестов).

- [ ] **Step 5: Коммит**

```bash
git add skills/consilium-principis/SKILL.md tests/test_plugin_manifests.py
git commit -m "feat(plugin): тонкий skill-консьерж (триггер+онбординг+указатель на MCP, без bash-вызовов scripts/)"
```

---

### Task 3: Нейтрализовать машинно-специфичный `mcp.json`

**Files:**
- Modify: `mcp.json`
- Test: `tests/test_plugin_manifests.py` (дописать один тест)

Контекст: сейчас корневой `mcp.json` содержит абсолютный путь конкретной машины
(`/Users/ilyautov/...` и `/opt/homebrew/...`) — машинный артефакт в версионируемом файле. Реальный
per-machine конфиг генерит `python3 scripts/board.py mcp-config`; плагин-установка поднимает MCP сама
через `.mcp.json`. Приводим `mcp.json` к нейтральному плейсхолдеру (как `mcp.example.json`).

- [ ] **Step 1: Дописать падающий тест** — добавить в конец `tests/test_plugin_manifests.py`:

```python
def test_tracked_mcp_json_has_no_machine_path():
    raw = (ROOT / "mcp.json").read_text(encoding="utf-8")
    assert "/Users/ilyautov" not in raw, "ничей локальный путь в версионируемом mcp.json"
    assert "/opt/homebrew" not in raw
    m = json.loads(raw)  # остаётся валидным JSON
    assert "consilium-principis" in m["mcpServers"]
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_plugin_manifests.py::test_tracked_mcp_json_has_no_machine_path -v`
Expected: FAIL (`AssertionError` — текущий `mcp.json` содержит `/Users/ilyautov`).

- [ ] **Step 3: Переписать `mcp.json`** на нейтральный плейсхолдер (совпадает с `mcp.example.json`):

```json
{
  "_comment": "Плагин-установка поднимает MCP сама (.claude-plugin/.mcp.json). Для ручного подключения путь под свою машину даёт: python3 scripts/board.py mcp-config",
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
    }
  }
}
```

- [ ] **Step 4: Запустить — зелёный**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_plugin_manifests.py -v`
Expected: PASS (6 тестов).

- [ ] **Step 5: Коммит**

```bash
git add mcp.json tests/test_plugin_manifests.py
git commit -m "chore(mcp): нейтрализовать машинный абсолют в mcp.json (плагин поднимает MCP сам; ручной путь — board.py mcp-config)"
```

---

### Task 4: README — `/plugin` золотой путь установки

**Files:**
- Modify: `README.md` (секция `## Установка`)

Нет теста — документация. Проверка: раздел визуально читается, ссылки/команды верны.

- [ ] **Step 1: Вставить блок плагина первым в `## Установка`.** Найти строку `## Установка` и сразу после неё (перед `**Самое простое — поставит сам Claude.**`) вставить:

```markdown
### Через Claude Code plugin (рекомендуется)

В Claude Code:

> `/plugin marketplace add ilyautov/consilium-principis`
> `/plugin install consilium-principis@consilium-marketplace`

Claude Code поднимет MCP-сервер и зарегистрирует навык. Потом скажи **«с чего начать»** —
консьерж проверит готовность и соберёт стартовый совет (Марк Аврелий + Эпиктет, public-domain).

### Или обычной установкой
```

(Существующий текст «Самое простое — поставит сам Claude…» и далее остаётся как fallback-путь под новым подзаголовком `### Или обычной установкой`.)

- [ ] **Step 2: Проверить рендер** — глазами: блок плагина стоит первым, команды `/plugin …` корректны, остальные пути ниже как fallback. Убедиться, что markdown не сломан (заголовки, блок-цитаты).

- [ ] **Step 3: Коммит**

```bash
git add README.md
git commit -m "docs(readme): /plugin marketplace как золотой путь установки №1, install.py — fallback"
```

---

## После всех задач

- [ ] **Весь сьют оффлайн:** `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` → 1072 прежних + 6 новых = зелёный (кроме env-flaky SSRF).
- [ ] **Selfdoc-дрейф:** добавлен `tests/test_plugin_manifests.py` → индекс selfdoc считает тесты. Перегенерировать и закоммитить: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`, затем `git add docs/selfdoc/index.json docs/MANUAL.md && git commit -m "docs(selfdoc): регенерация — +тест-гард манифестов плагина"`.
- [ ] **Финальное whole-feature ревью** перед мержем: манифесты валидны, версии синхронны, ноль абсолютов, skill без `scripts/`-вызовов, install.py-путь не тронут, ноль правок mcp_server/контура.
- [ ] Затем — `superpowers:finishing-a-development-branch` (мерж/пуш — firewall-ритуал, слово юзера).

## Замечания
- **Ручная проверка плагина (вне CI, опц.):** на чистой машине `/plugin marketplace add ilyautov/consilium-principis` → `/plugin install …` → сервер поднялся, `/consilium-principis` навык виден. Требует запушенного публичного репо — делается ПОСЛЕ мержа+пуша.
- `command: "python3"` — под macOS/Linux; Windows-пользователю может понадобиться `python` (известное ограничение, не блокер v0.1).
- Ноль правок `scripts/mcp_server.py`: если исполнителю кажется, что нужно менять сервер/контур/переносить `scripts` — он вышел за область, СТОП и эскалация.
