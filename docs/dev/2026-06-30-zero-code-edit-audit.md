# Аудит: zero-code-edit от установки до тюнинга из чистого MCP-хоста

**Дата:** 2026-06-30. **Вопрос Ильи:** весь флоу (установка → сборка → тюнинг, вплоть до ollama) —
напрямую из Cowork/любого агента, БЕЗ правок кода. Нужен ли отдельный MCP Cowork→ollama?

## База уже работает без кода и без ollama

- Гейт верности `best_match` — backend-независим (чистая подстрока, без ollama).
- `corpusbuild.pipeline.build` детерминирован (ingest→clean→chunk, без ollama).
- `retrieve` падает в лексический пол без семантики. `cite`/`fidelity_check` работают.
- Жизненный цикл уже тулами: build_advisor, build_lens, ingest_telegram, seed_council,
  scaffold_principis, validate_manifest, doctor, setup_full, calibrate…

Вывод: «поставил → собрал линзу → совет цитирует 🔵» идёт code-free на SIMPLE-тире. ollama = апгрейд
до FULL (семантик-ретрив + кернелы), не условие работы.

## Закрытые пробелы (2026-06-30, коммит см. git)

| пробел | было | стало (тул) |
|---|---|---|
| тюнинг | правка board_config.json руками | `config_get` / `config_set` |
| FULL-тир / ollama | install+старт демона лишь инструкцией | `ollama_status` / `ollama_ensure` (старт демона, если бинарь есть) / `ollama_pull` |
| корпус извне | текст только строкой; URL/большой том — через шелл | `add_source` (url+strip Gutenberg \| text \| path; ставит тир в manifest) |

Попутно: латентный баг `json` (импортировался лишь локально, голый `json.` в `_kernel_themes`
упал бы на советнике с kernels.json) — починен module-level импортом.

## Нужен ли отдельный MCP Cowork→ollama? — НЕТ

Наш сервер уже говорит с ollama напрямую (`setup_full` по HTTP, `embed.py`, kernels — через
localhost:11434). Хосту не нужен мост — сервер сам ходит в ollama. Чего не хватало — не моста, а
тулов жизненного цикла, и они теперь В НАШЕМ сервере (status/ensure/pull). Отдельный MCP = второй
конфиг-энтри, расщеплённая ollama-логика, и установку демона он всё равно не решает. Решение: НЕ
заводить.

## Неустранимо-ручные шаги (и это правильно)

1. **Первая установка бинаря ollama** — системный софт молча не ставим (outward-facing/hard-to-
   reverse). `ollama_ensure` возвращает точную команду под ТЕКУЩУЮ ОС (darwin/linux/windows из
   `setup_full.INSTALL_HINTS`, не только Mac); старт демона `ollama serve` — кросс-платформенно
   (POSIX setsid / Windows detached). Всё после (pull → сборка → тюнинг) — тулами.
2. **Регистрация самого MCP** (`mcp.json` в Cowork) — до-MCP, курица-яйцо. Разовый шаг / инсталлер.

## Безопасность add_source (тул дёргается хостом → возможна инъекция из веб-контента)

- **SSRF**: `collect_common.fetch` (public_only) — схема только http/https, host обязан резолвиться
  в ПУБЛИЧНЫЙ IP (нет loopback/private/link-local/reserved/metadata); редиректы ре-валидируются.
  `license` НЕ открывает egress (гард безусловен). Защищает и `collect_pd`.
- **Path traversal**: `path=` разрешён только ВНУТРИ корня репо (`realpath` под `_root()`); внешний
  файл — через `text=` или копию в репо.

## Замечание (вне скоупа)

`collect_common.land_to_sources` префиксит провенанс-`#`-хедер в .txt → на КРОШЕЧНОМ тексте он лезет
в чанк/цитату; на большом томе — только в начало первого чанка (потому у Макиавелли/Аврелия чисто).
Сайдкар `_provenance.jsonl` уже есть — хедер в тексте можно будет убрать отдельным срезом.
