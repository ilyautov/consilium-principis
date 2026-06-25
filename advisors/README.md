# advisors/ — твоя личная доска (user-data, НЕ в репозитории)

Эта папка — **instance-данные**, а не код скилла. Всё её содержимое (кроме этого README)
исключено из git: персоны, корпуса, эмбеддинги и **приватные `relationship.md`** (твои решения
и их исходы по петле U1) остаются только на твоей машине.

Причина разделения:
- **Легальность** — корпуса (`sources/`, `corpus.jsonl`) могут содержать твои легальные копии
  чужих книг; они не редистрибутируются.
- **Приватность** — `relationship.md` хранит твои реальные решения и исходы. Им не место в репо.
- **Под других** — репо = переносимая машинерия; каждый собирает СВОЮ доску локально.

## Как собрать советника
```
mkdir -p advisors/<slug>
# 1) положить источники: collect_pd (PD) / collect_web / collect_transcript, либо вручную в sources/
python3 scripts/collect_pd.py advisors/<slug> --url <gutenberg-url>
# 2) собрать корпус + кандидаты цитат
python3 scripts/build_advisor.py advisors/<slug> --name "<Имя>"
# 3) написать persona.md (см. структуру у уже собранных), цитаты проверить через verbatim_in_corpus
# 4) тир + конфиг, при наличии ollama — семантический индекс
python3 scripts/board_init.py advisors --semantic-available true
python3 scripts/tier_full.py advisors/<slug>      # если FULL-тир
# 5) golden-набор в scripts/golden/<slug>.{retrieval,abstention}.jsonl и проверка
python3 scripts/eval.py advisors/<slug>
```

Структуру `persona.md` (конституция / как спорит / never_do+never_quote / quote_bank 🔵 / challenge)
повторяй с любого уже собранного советника.
