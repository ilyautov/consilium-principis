# HANDOFF → Claude Code

Передача проекта «Личный совет директоров» в код-контур для доработки tier-FULL и eval.
Дата: 2026-06-10. Контур-источник: Cowork-сессия (дизайн + прототипы собраны).

## Что это
Cowork/Claude Code скилл: личный совет директоров из AI-персонажей реальных мыслителей.
Пользователь выбирает фигуры, приносит легальные материалы, скилл строит профили и проводит
заседание-форум. Ров = защитный контур (гигиена против эхо-камеры/фейк-цитат), не сам совет.
Полный замысел: `ARCHITECTURE-personal-board-skill.md` (17 разделов). Ресёрч: `RESEARCH-personal-board.md`.

## Граница «что в код / что декларативно» (важно)
- **В КОД (этот репо):** tier-FULL движок (семантика, abstention, реранк, grounded-gen), eval-харнесс.
  Переиспользовать Гефест, НЕ писать заново.
- **ДЕКЛАРАТИВНО (остаётся скиллом):** оболочка — оркестрация заседания, профили, форум-виджет,
  защитный контур, `personal-board/SKILL.md`. Вызывает движок через адаптер (сигнатура
  `вопрос → грунтованные чанки со score`), про кишки движка не знает.

## Текущее состояние (что РАБОТАЕТ и прогнано)
- `personal-board/SKILL.md` — связующий файл: команды, защитный контур, формат заседания (форум
  4 такта), память 3 слоя, авто-tier, легальная граница.
- `scripts/build_advisor.py` — ingest материалов → corpus.jsonl + quote_candidates (прогнан).
- `scripts/diversity_check.py` — ортогональность состава, анти-эхо-камера (прогнан: наша тройка 0.96).
- `scripts/board_init.py` — авто-tier simple/full по размеру корпуса + бэкенд (прогнан → board_config.json).
- `scripts/eval.py` — fidelity-метрика работает; retrieval/abstention/challenge — спека.
- `advisors/{munger,naval,marcus-aurelius}/persona.md` — слой 0 (конституция, quote_bank с tier).
- `council/sessions/2026-06-10-...md` — лог первого заседания (Pre-Mortem).
- Среда: ollama жив, `bge-m3` + `qwen2.5` доступны (tier-FULL реален).

## EVAL — первоклассно, НЕ забывать (живой результат уже есть)
`python3 scripts/eval.py advisors/munger advisors/naval advisors/marcus-aurelius`
- **FIDELITY [работает]:** цитата из quote_bank дословно в корпусе? **Поймал реальную дыру:**
  Аврелий 0/8 — quote_bank залит переводом Hays, а корпус загружен из другого источника
  (sample). Это та самая фабрикация атрибуции, если выдать как 🔵. **Первая задача — починить:**
  либо грузить корпус того же издания, что цитаты, либо тянуть цитаты из загруженного корпуса.
- **RETRIEVAL [спека]:** golden {вопрос→чанк} → top-1/top-3 (как Гефест `engine/semantic_eval.py`).
- **ABSTENTION [спека]:** вопросы вне корпуса → % честных отказов, цель 0% галлюцинаций
  (порог `abstain_threshold` 0.62 из board_config, перенос Гефеста `eval_abstention.py`).
- **CHALLENGE-RATE [спека]:** парсить council/sessions → доля заседаний, где совет оспорил юзера
  (анти-sycophancy, наша ключевая метрика).

## Следующие шаги в Claude Code (приоритет)
1. **Починить fidelity-дыру** (Аврелий 0/8): согласовать quote_bank ↔ загруженный корпус.
2. **Достроить eval** (retrieval golden-набор, abstention, challenge-rate) — без него точность = вера.
3. **Интегрировать Гефест tier-FULL как зависимость** (НЕ переписывать). Точки переиспользования:
   - `personal/pilots/rag-sds/engine/backends.py` — вендор-нейтр. адаптер эмбеддингов/генерации.
   - `.../engine/build_semantic_index.py` — bge-m3 индекс (батчевый /api/embed).
   - `.../engine/semantic_rerank_eval.py` — кросс-энкодер bge-reranker-v2-m3.
   - `.../engine/eval_abstention.py` — abstention-метрика и порог.
   Замер Гефеста (ориентир): лексика 60 → bge-m3 84 → +реранк 92 top-1.
4. **Exact-match гейт цитат** в `fidelity_check`: 🔵 только при дословном совпадении + score>порог, иначе 🟡.
5. **Консолидировать раскладку:** SKILL.md ждёт `scripts/` и `advisors/` рядом с собой; сейчас в корне.
6. **U1 track-record** (слой 1 пишет ИСХОД) — отложен, кандидат №1 на ценность.

## Открытые DP (см. ARCHITECTURE раздел 11)
DP-1 фигуры · DP-2 индексация (закрыт авто-tier) · DP-3 выбор режима · DP-4 legal-глубина ·
DP-5 аудитория · DP-6 первый режим (Pre-Mortem). Ставки проставлены в разделе 11.

## Легальная граница (соблюдать в коде)
Скилл книги НЕ качает. Пользователь кладёт легальные копии в `advisors/{name}/sources/`.
`.gitignore` исключает `sources/` и `corpus.jsonl` — НЕ коммитить чужие тексты.

## Запуск
```bash
python3 scripts/board_init.py advisors --semantic-available true   # выбор tier
python3 scripts/build_advisor.py advisors/{name} --name "{Имя}"    # ingest
python3 scripts/diversity_check.py advisors/a advisors/b ...        # состав
python3 scripts/eval.py advisors/a advisors/b ...                  # точность
```

## Честные ограничения (Evidence Gate)
- Ценность совета vs baseline не доказана числом (заблуждение #2, ARCHITECTURE р.15). Нужен слепой A/B.
- Числа Гефеста на ЕГО домене; на корпусе советника переснять.
- Малые корпуса не требуют tier-FULL (Via Negativa) — не тащить стек ради стека.
- Промпт-защита от sycophancy слаба без steering; дрейф персоны в корне не решён.
