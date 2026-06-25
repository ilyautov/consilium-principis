# Corpus Builder / Rebuilder & Enrichment — Design

> Статус: DESIGN (2026-06-25). Backbone под provenance-схему и eval-матрицу. Заменяет наивный
> `build_advisor.py` (ingest+chunk+candidates) на staged, идемпотентный, версионируемый конвейер.

## 0. Зачем

Всё, что мы строим (тиры, чистка границ, S1-ингест, мост, кернелы, граф), упирается в сборку
корпуса. Текущий билдер не умеет: чистить фронт-маттер (интро переводчика уехало в P1), пер-регионные
тиры, авто-кодировку, энричмент, линковку, версионирование, инкрементальную пересборку. Для
«большой разнородной матрицы» нужен ОДИН параметрический билдер → много вариантов корпуса,
и каждый eval-результат привязан к конкретной сборке (воспроизводимость).

## 1. Архитектура: staged pipeline, manifest-driven, content-hash cache

`build(advisor, config) → versioned artifacts`. Каждая стадия — (входные артефакты, config) →
выходной артефакт, кэш-ключ = hash(входы + версия стадии + config). Пересобирается только изменённое.

```
1. INGEST        многоформат (txt/md/pdf/epub) + АВТО-кодировка (chardet/try-list) → текст с позицией
2. CLEAN+BOUND   на источник: boilerplate→strip · фронт-маттер→B/S1 · TOC→exclude · тело→P1 · notes→S1
3. PROVENANCE    манифест: tier/attribution/license/lang + пер-РЕГИОН body-маркеры; дефолт fail-closed=A
4. CHUNK         СТРАТЕГИЯ-ПЛАГИН (size/overlap/sentence-aware/parent-doc) ← ось эвала
5. ENRICH ⟂      [P1] LLM-мост (decode/примеры/кросс-домен/осовременивание) — отдельный store, derived, не 🔵
6. LINK/GRAPH    [P1] рёбра: kernel→пассаж · S1→P1 (вербатим-цитата + nearest) · provenance-граф
7. KERNELS       [P1] извлечь+провалидировать мета-идеи (exp_kernels уже есть), хранить заземлёнными
8. INDEX         lexical + semantic, ОБА tier-aware, пересобираются вместе
```

## 2. Артефакты (data model)

```
advisors/<slug>/
  sources/                       # raw (gitignore) + manifest.json (провенанс + body-маркеры)
  build/                         # генерируемое (gitignore)
    corpus.jsonl                 # {id, source, tier, region, start, end, text}
    enrichment.jsonl             # {id, kind, derived_from:[chunk_id...], tier:"derived", never_quote:true, text}
    graph.jsonl                  # {src_id, dst_id, type, weight}
    kernels.json                 # [{name, method, grounded_in:[chunk_id...], validated:bool, val_score}]
    build.lock.json              # воспроизводимость (см. §4)
  data/embeddings_<slug>.npy     # semantic index (gitignore, имя матчит .gitignore)
```

Чанк теперь несёт `tier` явно (не только через джойн к манифесту) — тир «запекается» на стадии 3,
чтобы индекс и fidelity-гейт были tier-aware без повторного джойна.

## 3. Манифест: пер-регионные тиры

Один гутенберг-файл = boilerplate + интро(B) + TOC + тело(P1) + notes(S1). Тир на РЕГИОН:

```json
"meditations-long-gutenberg.txt": {
  "tier": "P1", "attribution": "Marcus Aurelius", "lang": "en", "license": "public-domain",
  "regions": [
    {"tier": "B",  "until": "THE FIRST BOOK"},
    {"tier": "P1", "from": "THE FIRST BOOK", "until": "APPENDIX"},
    {"tier": "S1", "from": "APPENDIX"}
  ]
}
```

Нет `regions` → весь файл = top-level `tier`. Нет манифеста → всё P1 (бэк-компат, миграция нулевая).
Маркеры — строки/regex; CLEAN режет по первому вхождению. Один раз на источник, дёшево.

## 4. build.lock.json — воспроизводимость (для статистики)

```json
{
  "built_at": "<передаётся аргументом, не Date.now>",
  "config_hash": "...",
  "sources": {"the-prince-marriott.txt": "sha256:...", "tarasov-...txt": "sha256:..."},
  "config": {"chunk": {"strategy": "size", "target": 900, "overlap": 180}, "enrich": false,
             "embed_model": "bge-m3"},
  "stages": {"ingest": "v1", "clean": "v1", "chunk": "v1", "index": "v1"},
  "counts": {"P1": 1488, "S1": 630, "chunks": 2118}
}
```

Любой eval ссылается на `config_hash` → результаты сравнимы только в рамках одной сборки; смена
чанкинга/состава = новая сборка = новая строка матрицы. Инкрементальность: source-hash не изменился
и стадия не бампнута → берём кэш.

## 5. Валидационный гейт (доктор корпуса)

После сборки печатает и проваливает на нарушениях:
- распределение по тирам; **флаг неразмеченного** (попал в fail-closed A) — требует решения;
- **нет S→🔵 утечки**: ни один enrichment/S1/B-чанк не в lexical/fidelity-пуле как 🔵-eligible;
- вербатим-спот-чек: сэмпл цитат → 🔵 только если матч в P1/P2;
- (P1) валидация кернелов: held-out дискриминация > случайной — **count-matched (равное число
  кернелов обе стороны) + мульти-seed усреднение**. Эксперимент B показал: own-win через max-cos
  смещён числом кернелов, а извлечение gemma шумит ~11пт между seed'ами → без этих двух поправок
  цифра недостоверна. Под-корпусная структура (per-source) НЕ помогает (88.9% ≤ flat-12 92.3%).

## 6. Связь с текущим кодом

- `build_advisor.py` → рефактор в стадии (ingest/clean/chunk/candidates). Внешний CLI сохраняем.
- `tier_full.py` → стадия 8 (semantic index), вызывается билдером, tier-aware meta.
- `engine/provenance.py` (новый) → `tier_of(chunk)`, грузит манифест; юзается стадией 3 и fidelity.
- `engine/fidelity.py` → ключуется на `chunk.tier` (🔵 только P1/P2; S→блок мисатрибуции).
- `corpus.jsonl` переезжает в `build/` (обновить пути в engine/eval — один корень-резолвер).

## 7. CLI / интерфейс

```
python3 scripts/corpus_build.py advisors/<slug> [--config build.json]
        [--stages clean,chunk,index] [--force] [--report]
```
Без `--stages` — полный (инкрементальный) прогон. `--report` — только доктор (§5). Config-файл
опционален (дефолты = текущее поведение: size-чанкинг 900/180, enrich off, bge-m3).

## 8. Scope: P0 → P1

> «Сразу хорошо» (2026-06-25): без shortcut'ов. Чистая `build/`-раскладка и сквозной провенанс
> делаются с первого раза в P0 (никакого «оставим corpus.jsonl на месте ради churn»). P0/P1 —
> это ПОРЯДОК (фундамент раньше энричмента), а не «P0 наспех».

**P0 — корректный воспроизводимый билдер** (стадии 1-4, 8 + build.lock + доктор + provenance.py +
tier-aware fidelity + рефактор путей в build/). Чинит фронт-маттер-загрязнение, делает пересборку
дешёвой/воспроизводимой, разблокирует чистый тест моста A. Бэк-компат: советники без манифеста
собираются как раньше.

**P1 — ров и ценность** (стадии 5-7): enrichment-генерация (калиброванный мост), S1→P1 линковка,
kernel-граф с заземлением. Опирается на P0.

## 9. Риски

- **Чистка границ ломает корпус** (отрезали лишнее/мало): доктор печатает первые/последние строки
  каждого региона на сборку — глазами видно. Маркеры — в манифесте, правятся вручную.
- **Кэш отдаёт стейл**: ключ включает версию стадии; бамп версии = форс-пересборка стадии.
- **Пути build/**: единый резолвер `corpus_path(advisor)`, чтобы engine/eval/doctor не разъехались.
- **Энричмент дрейфует** (P1): всегда derived+never_quote, трасса к источнику, доктор проверяет
  отсутствие в 🔵-пуле. Человеческий S1 (Тарасов) безопаснее синтетического — приоритет ему.
