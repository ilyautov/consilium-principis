# Дизайн: переносимый тирированный движок (Consilium-Principis)

Дата: 2026-06-23 · Статус: согласован к написанию плана
Подход: **A+C** — in-process адаптер с N бэкендами, контракт MCP-совместимой формы.

## Зачем

Проект перерос «просто скилл»: движок (семантический ретрив через Гефест/ollama) стал
service-образным, а скилл шеллит Python и завязан на раскладку путей. Цель — **одна стабильная
граница** между скиллом и ретривом, за которой переносимые тиры:
- **минимальный кит** — скилл-only, 0 установки (работает на любой машине, где есть Claude+Python);
- **максимум** — локальный ollama bge-m3 (семантика), что «Claude настроил»;
- **remote** — хостед-инфра, к которой ходишь с любого компа (только seam, не строим сейчас).

Скоуп: **под себя сейчас, контракт — под других потом** (seam под auth/remote, без мульти-тенантности).

## Несущий принцип

`fidelity_check` («цитата дословно в корпусе?») — это substring-матч, эмбеддинги не нужны →
**защитный контур работает даже на 0-install полу**. Деградирует только *качество ретрива*, не
*честность*. Минимальный кит — честный минимум, не кастрат. Это оправдывает существование пола.

## Архитектура

```
СКИЛЛ (декларатив: SKILL.md + персоны) → зовёт resolve_engine()
   ▼
КОНТРАКТ  Engine (ABC, MCP-совместимые сигнатуры)
   retrieve · abstain_check · fidelity_check · build_index
   ├─ LexicalEngine   stdlib, 0-install ПОЛ
   ├─ SemanticEngine  обёртка tier_full/Гефест (ollama bge-m3), гибридный retrieve
   └─ RemoteEngine    интерфейс-заглушка (seam)
   ▲
RESOLVER  resolve_engine(advisor): remote(настроен?) → semantic(ollama жив?) → lexical(всегда)
```

### Контракт (MCP-форма, дисциплина C)
- `retrieve(question, advisor, top_k=3) -> list[Passage]`  · `Passage{text, score, source}`
- `abstain_check(question, advisor) -> AbstainResult{abstain: bool, max_score: float, threshold: float}`
- `fidelity_check(quote, advisor) -> FidelityResult{status: "🔵"|"🟡", verbatim: bool, source: str}`
- `build_index(advisor) -> dict` (meta; для lexical — no-op)

Имена/возвраты совпадают с будущими MCP-инструментами → MCP-фасад и RemoteEngine встают поверх
ядра без переписывания. Коллекторы (`collect_*`) — **build-time CLI**, НЕ в горячем контракте
(в MCP могут выехать отдельной группой инструментов позже).

## Компоненты (файлы)

| Файл | Роль |
|---|---|
| `scripts/engine/__init__.py` | контракт `Engine` ABC + dataclasses + `resolve_engine()` |
| `scripts/engine/lexical.py` | `LexicalEngine` (перенос текущего лексического fallback) |
| `scripts/engine/semantic.py` | `SemanticEngine` (обёртка `tier_full`; гибридный retrieve) |
| `scripts/engine/fidelity.py` | общий verbatim-чек, used by all backends |
| `scripts/engine/remote.py` | `RemoteEngine` заглушка (endpoint+token из конфига, логики нет) |
| `scripts/doctor.py` *(опц.)* | отчёт «какой tier доступен на этой машине» |

Рефактор: `eval.py`, `board_init.py`, `SKILL.md` зовут `resolve_engine`, не импортят `tier_full`.
MCP-фасад — отложен: схема зафиксирована здесь, файл не шипим.

## Поток данных

**Query-time:** созыв → `engine = resolve_engine(advisor)` → `abstain_check` (abstain → честный
отказ) → иначе `retrieve` → grounded-ответ → на цитату `fidelity_check` → маркер 🔵/🟡.

**Build-time:** `collect_*` → `sources/` → `build_advisor` → `corpus.jsonl` → (semantic)
`build_index` пишет эмбеддинги И записывает `{chunk_chars, abstain_threshold}` в board_config.

## Обработка ошибок и деградация (first-class)

- ollama упал / Гефест отсутствует → SemanticEngine падает → резолвер ловит → `LexicalEngine` +
  warning. **Никогда не крэшит; fidelity продолжает работать.**
- **Кэш vs деградация (разрешение противоречия):** `resolve_engine` кэширует выбранный бэкенд
  по ключу `advisor` на процесс, НО при runtime-падении бэкенда (ollama умер mid-session) метод
  ловит исключение → **инвалидирует кэш этого advisor и пере-резолвит вниз** (semantic→lexical).
  Так «never crash» держится даже посреди заседания, а не только на старте.
- **Связь порог↔chunk-size** (найденный баг): `build_index` записывает `chunk_chars` рядом с
  индексом; `abstain_check` читает записанное, не глобальный дефолт; рассинхрон → warn.
- RemoteEngine не настроен → резолвер молча пропускает; запрошен явно но не настроен → внятная
  ошибка.
- Контракт гарантирует единообразные формы возврата у всех бэкендов → MCP-фасад позже тривиален.

## Переносимость

- Пути резолвятся относительно пакета (PROJECT_ROOT), не cwd — лечит path-coupling, что мы ловили.
- На свежей машине без Гефеста: семантика недоступна → пол (лексика + fidelity) всё равно работает.
- `doctor.py` сообщает доступный tier — помогает «0-install юзеру» понять, что у него есть.

## Тестирование

- `eval.py --engine lexical|semantic` (дефолт resolved): лексический пол → fidelity 6/6 + вменяемый
  abstention; semantic → лучше retrieval (гибрид поднимает thematic-inexact).
- **Contract-conformance**: каждый бэкенд возвращает корректно-формные dataclass'ы (юнит).
- **Degradation-тест**: форс ollama-absent → резолвер даёт LexicalEngine, fidelity 6/6, без крэша.
- Golden-наборы переиспользуются.

## Фазы реализации (для плана)

1. **Ядро**: контракт + dataclasses + `fidelity.py` (общий) + `resolve_engine`.
2. **LexicalEngine**: перенос fallback → бэкенд; пол зелёный (fidelity 6/6, abstention).
3. **SemanticEngine**: обёртка `tier_full` за контрактом; eval паритет с текущим.
4. **Рефактор потребителей**: `eval.py`/`board_init.py`/`SKILL.md` → `resolve_engine`.
5. **Деградация + chunk/threshold-запись** + degradation-тест.
6. *(отдельная фаза, качество)* **Гибридный retrieval** в SemanticEngine — фикс thematic-inexact.
7. *(опц.)* `doctor.py`.
8. **Seam**: `RemoteEngine` заглушка + зафиксированная MCP-схема (не реализуем).

## Вне скоупа (явно)

- MCP-сервер (фасад) — отложен; только схема.
- Remote-хостинг, auth, мульти-тенантность — только seam.
- Легальность чужих корпусов для дистрибуции — отдельное решение, когда пойдём «для других».
