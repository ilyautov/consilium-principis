# advisors/ — твоя личная доска (user-data, НЕ в репозитории)

Эта папка — **instance-данные**, а не код скилла. Всё её содержимое (кроме этого README)
исключено из git: персоны, корпуса, эмбеддинги и **приватные `relationship.md`** (твои решения
и их исходы по петле U1) остаются только на твоей машине.

Причина разделения:
- **Легальность** — корпуса (`sources/`, `corpus.jsonl`) могут содержать твои легальные копии
  чужих книг; они не редистрибутируются.
- **Приватность** — `relationship.md` хранит твои реальные решения и исходы. Им не место в репо.
- **Под других** — репо = переносимая машинерия; каждый собирает СВОЮ доску локально.

## Самое простое — попроси ассистента
Скажи Claude **«с чего начать»** (соберёт стартовый совет PD-мудрецов) или **«добавь советника — <Имя>»**
(проведёт за руку). Под капотом — команды ниже.

## Стартовый совет в один шаг (public-domain)
```
python3 scripts/board.py seed-council    # Аврелий + Эпиктет: fetch → манифест → валидация → corpus → kernels → индекс
```

## Свой советник — в один шаг
```
# 1) источники в advisors/<slug>/sources/ : collect_pd (PD) / collect_web / collect_transcript, либо легальные копии вручную
python3 scripts/collect_pd.py advisors/<slug> --url <gutenberg-url>
# 2) тир-манифест sources/manifest.json — РАЗМЕТКА ТИРОВ (слова автора → P1; комментарий → S1; предисловие → B).
#    Решение о тире — твоё/ассистента; проверь, что region-маркеры реально в тексте (иначе ров течёт):
python3 scripts/board.py validate-manifest advisors/<slug>
# 3) собрать целиком: манифест-гейт → corpus → kernels → семантический индекс (graceful без ollama)
python3 scripts/board.py build-advisor advisors/<slug>
# 4) написать advisors/<slug>/persona.md (структуру повторяй с уже собранного советника)
# 5) golden-набор в scripts/golden/<slug>.{retrieval,abstention}.jsonl и проверка
python3 scripts/eval.py advisors/<slug>
```

Структуру `persona.md` (конституция / как спорит / never_do+never_quote / quote_bank 🔵 / challenge)
повторяй с любого уже собранного советника. Проверить отдельную цитату:
`from engine.fidelity import best_match` → `best_match("<цитата>", "advisors/<slug>")` → `('P1', источник)` = годна на 🔵.
