# Провенанс moat-базлайна и заморозка golden

**Зачем.** `scripts/moat_check.py` сравнивает свежий прогон рва с замороженным базлайном
`docs/dev/moat-baseline.json`. Батарея камуфляжа (метрика `misapply_rate`) уже лежит в
репо (`scripts/moat_battery/<slug>.camouflage.jsonl`). А answerable-набор для метрики
`coverage` брался из `scripts/golden/`, который был gitignored целиком → на чистой машине
и в CI базлайн был **невоспроизводим**. Ниже — что и почему заморожено (F #1, 2026-07-21).

## Что заморожено (ровно 5 файлов)

`run_battery` → `_answerable_rows` → `eval.load_golden(slug, "retrieval.en" | "retrieval")`.
То есть базлайну нужен ТОЛЬКО retrieval-слайс. Заморожены:

| файл | источник (все PD) |
|---|---|
| `scripts/golden/machiavelli.retrieval.en.jsonl` | «The Prince», перевод W. K. Marriott, Gutenberg #1232 |
| `scripts/golden/machiavelli.retrieval.jsonl` | то же (RU-вопросы к тем же PD-главам) |
| `scripts/golden/marcus-aurelius.retrieval.en.jsonl` | «Meditations», перевод George Long (PD) |
| `scripts/golden/marcus-aurelius.retrieval.jsonl` | то же |
| `scripts/golden/sun-tzu.retrieval.en.jsonl` | «The Art of War», перевод Lionel Giles (PD) |

Каждая строка — триплет `{q, anchor, ref}`: `anchor` — короткая (<15 слов) фраза из PD-текста,
`ref` — глава PD-источника. Ни длинных пассажей, ни вторичной литературы.

## Что НЕ заморожено и почему (firewall)

- **Слайсы приватных советников** (`<приватный-слаг>.*` — реальные живые люди) — НИКОГДА в git.
  `.gitignore` держит их через `scripts/golden/*` без негейшна; firewall-хук — вторая страховка
  (список приватных имён он выводит из локального `advisors/`, в репо их имён нет).
- **`*.answerable.v2` / `*.abstention` / `*.auto`** — базлайну не нужны (он читает `retrieval*`),
  и `machiavelli.answerable.v2` привязан к смешанному retrieval-корпусу (PD-«Государь» + вторичная
  литература под копирайтом, ~1924 чанка) — заморозка утащила бы копирайт. Оставлены локальными.

**Важно про «своеобразный» корпус Макиавелли:** копирайт-вторичка живёт только в retrieval-**корпусе**
(`advisors/machiavelli`, не в репо), а замороженный retrieval-**голден** привязан исключительно
к PD-«Государю» — вторичка в git не попадает. Поэтому Макиавелли-слайс морозить безопасно.

## Как регенить golden (локально)

Retrieval-golden собирается вручную из PD-первоисточников (вопрос + якорная фраза + ссылка на
главу). Это не LLM-генерация — набор стабилен и правится точечно. При добавлении нового PD-советника
в базлайн: собери `<slug>.retrieval.en.jsonl` из его PD-корпуса, добавь негейшн-строку в `.gitignore`,
пересчитай базлайн (`python3 scripts/moat_check.py --write-baseline`, нужен судья) и обнови эту доку.
