# Retrieval/abstention regression-гейт — refresh-ритуал (слой 3)

Спека: `docs/superpowers/specs/2026-07-18-accuracy-measurement-proposal.md`, узел 2, Вариант C.

Гейт разнесён на три слоя, чтобы не слить в один флейки-тест две разные регрессии:

| Слой | Что ловит | Где живёт | Требует сети? |
|------|-----------|-----------|----------------|
| 1 — emit | сериализация метрик со стратами | `eval.py --emit-metrics` | нет (может и на lexical) |
| 2 — gate | регресс КОДА метрик/порогов | `tests/test_retrieval_regression.py` + `scripts/retrieval_regression.py` | **нет** (замороженные скоры) |
| 3 — refresh | регресс ДВИЖКА/индекса | **этот ритуал, у владельца** | да (ollama + bge-m3) |

Слой 2 (блокирующий, на каждый PR) НЕ зовёт живой `retrieve` — он гоняет математику
(`abstention_curve` + top-k доли) над замороженными скорами и сравнивает с baseline. Поэтому он
детерминирован и уважает офлайн-инвариант. Он НЕ заметит, что сам движок стал хуже, если фикстура
старая — это работа слоя 3.

## Когда запускать слой 3

Перед релизом / после смены корпуса, эмбеддера, чанкинга, порогов, ранкера — то есть всего, что
меняет ЖИВЫЕ скоры. Только на машине с поднятым `ollama` + `bge-m3` (tier-FULL).

## Шаги (на semantic-машине владельца)

1. Пересчитать живые метрики стратифицированно:
   ```
   python3 scripts/eval.py advisors/machiavelli advisors/marcus-aurelius advisors/sun-tzu \
       --engine semantic --emit-metrics docs/dev/retrieval-baseline.json
   ```
   Это перезапишет baseline числами семантического движка + `backend: "semantic"` +
   per-advisor `corpus_sha256`.

2. **Human-review диффа** (git diff baseline): глазами сверить, что метрики не просели молча.
   RU/EN/OOC — раздельно. Просадку принять ОСОЗНАННО (иначе гейт бесполезен) либо откатить
   изменение, её вызвавшее.

3. Обновить замороженные скоры-фикстуры для слоя 2 (когда producer будет добавлен):
   `tests/fixtures/scores/<slug>.<backend>.json` — per-question `ooc_scores` / `ans_scores` /
   `retrieval.<lang>.{hit1,hit3}`. Схема — в докстринге `retrieval_regression.metrics_from_frozen`.
   Фикстуры фиксируют скоры движка на момент refresh; слой 2 гоняет по ним математику каждый PR.

4. Прогнать блокирующий гейт локально:
   ```
   python3 scripts/retrieval_regression.py tests/fixtures/scores/<slug>.<backend>.json \
       docs/dev/retrieval-baseline.json
   ```
   Код возврата 1 = регресс (или `corpus_sha256` разошёлся = baseline stale).

## Что НЕ автоматизируем (YAGNI, спека §3)

- LLM-судья релевантности в блокирующем гейте (нарушит инвариант — сеть).
- Автогенерация golden в CI (`gen_golden` требует ollama).
- Автообновление baseline: апдейт при легитимном улучшении делает ЧЕЛОВЕК осознанно (шаг 2).

## Мягкий третий страж (уже есть)

`golden_meta.warn_on_drift` (`eval.py`) продолжает громко предупреждать в stderr при дрейфе
golden↔корпус — самый мягкий слой, не блокирует.
