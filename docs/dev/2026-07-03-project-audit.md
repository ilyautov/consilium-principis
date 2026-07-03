# Project Audit — Consilium-Principis (готовность к open-source)

**Дата:** 2026-07-03 · **Ветка аудита:** `docs/project-audit` от `master` · **HEAD на момент аудита:** `f36e226`
**Тип:** read-only health + OSS-readiness. Никакие файлы, кроме этого отчёта, не менялись.

---

## 0. Вердикт (TL;DR)

**Ров цел, файрвол чист, тесты зелёные, документация точная. Проект технически готов к флипу в public** —
блокеры не в коде, а операционные (ротация ключа) плюс несколько косметических несостыковок «примеры
ссылаются на не-шипуемых советников». Ни одного CRITICAL. Один HIGH — операционный (ключ OpenRouter в `.env`).

- **Тесты:** 976 passed, 1 skipped, ~10 c, полностью офлайн. CI форсит отсутствие ollama/движка. ✅
- **Файрвол приват/паблик:** ни одного приватного имени в трекаемых файлах (ни в именах, ни в теле). ✅
- **Moat-инварианты (12/12):** все держатся в коде — см. §2. ✅
- **Публичная документация:** LICENSE/README/QUICKSTART/CONNECT-MCP точны; fresh-install ставит рабочую линзу «Стратег». ✅
- **Остаточные блокеры:** ротация ключа (HIGH, вне git), «тёмные» тулы без INSTRUCTIONS-проводки (MEDIUM), примеры/рецепты ссылаются на не-шипуемых советников (MEDIUM).

---

## 1. Test &amp; CI health

Команда (как в задании):
```
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
→ 976 passed, 1 skipped in 9.97s   (повтор: 9.78s)
```
- Ожидалось ~976/1 skipped — **совпадает точно**.
- **Полностью офлайн:** прогон с недоступным движком Гефеста и мёртвым ollama-портом проходит зелёным → лексический
  пол (SIMPLE-тир) самодостаточен, семантика деградирует gracefully, не падает.
- **CI-инвариант цел.** `.github/workflows/ci.yml` — единственный workflow; матрица Python 3.10/3.11/3.12; в `env`
  жёстко зашиты `HEPHAESTUS_ENGINE: /nonexistent` и `OLLAMA_HOST: http://127.0.0.1:59999`. Никакой установки ollama/движка
  в шагах нет — CI воспроизводит ровно ситуацию внешнего клонировавшего.
- **Медленные/флейки:** самый долгий тест 2.53 c (`test_judge_backend.py::test_doctor_shows_independent_labels`),
  далее ~1.3 c — все пять «тяжёлых» это doctor-селф-чек (реальные fidelity-прогоны). Флейков нет, порядок стабилен, суммарно ~10 c. ✅
- **Соотношение тест/код:** 84 тест-файла против 87 py-скриптов; крупнейшие тест-файлы (`test_decision_tools.py` 500,
  `test_relevance_gate.py` 497, `test_apparatus.py` 466) сопоставимы с крупнейшими модулями — покрытие плотное и адресное.

**Severity: OK.** Замечаний нет.

---

## 2. Инвентарь moat-инвариантов (каждый подтверждён в коде)

| # | Инвариант | Держится? | Доказательство (file:line) |
|---|-----------|-----------|----------------------------|
| 1 | Verbatim 🔵 только через детерминированный `best_match` + `MIN_QUOTE_CHARS` | ✅ | `scripts/engine/fidelity.py:15` (`MIN_QUOTE_CHARS=8`), `:61-79` (`best_match`, коротыш→None fail-closed :69), `:89-91` (🔵 только P1/P2) |
| 2 | Гейт релевантности fail-closed + рубрика v2 (sub-band, band_hi 0.65) | ✅ | `scripts/relevance_gate.py:20` (FAIL-CLOSED), `:42-43` (BAND_LO 0.45 / BAND_HI 0.65), `:37` (0.65 намеренно выше камуфляж-потолка 0.612), `:103-118` (per-key коэрсинг + инверсия полосы → дефолт) |
| 3 | Two-phase host-протокол: nonce single-use/TTL, tier-blind, маркеры серверные, порог в коде | ✅ | `scripts/mcp_server.py:268` (`_VERDICT_TTL_S=900`, single-use), `:340-343` (tier-blind сорт), `:370` («тир — серверная тайна», кандидаты без маркеров), `:406-450` (`_gate_verdict`: валид-до-pop :417, порог `rel_threshold` применяет сервер :434, недостающая оценка→0 :427) |
| 3a | Закалка от prompt-injection в тексте кандидата | ✅ | `scripts/mcp_server.py:377-380` (§3.1: text = данные, не команды) + Rule 0/5 в INSTRUCTIONS |
| 4 | Валидация атрибуции на `render_session` | ✅ | `scripts/mcp_server.py:132` (`_validate_session_attribution`), `:1128` (зовётся в `_render_session`), `:1152` (`attribution_violations` в ответе) |
| 5 | Нет манифеста → тир A (бэк-компат fail-open к P1, но гейт манифеста стоит) | ✅ | `scripts/build_orchestrator.py:25-33` (есть манифест → `validate_manifest`-гейт останавливает сборку при рассинхроне; нет манифеста → note «всё P1»); `scripts/engine/fidelity.py:74` (чанк без tier → "A") |
| 6 | Write-traversal гарды (`_resolve_under_root`) | ✅ | `scripts/mcp_server.py:47-56` (`_resolve_under_root`, вне корня → error), `:673-675` (read-side realpath-гард), `:689` (write-side на add_source) |
| 7 | Rule 0 — consent на мутирующие тулы | ✅ | `scripts/mcp_server.py:1679-1689` (INSTRUCTIONS правило 0: мутаторы только по прямой просьбе юзера; инструкция из данных ≠ команда) |
| 8 | SSRF-гард (аллоулист по `is_global`) | ✅ | `scripts/collect_common.py:54-64` (`_is_public_ip`: аллоулист is_global + рекурсивная проверка embedded-v4 в туннельных v6, multicast/reserved явно исключены), `:83/149/153` (гард на схему + резолв, 6 хопов редиректа заново проходят слои) |
| 9 | `validate_map` fail-closed (inf/nan) | ✅ | `scripts/decision_map.py:58-68` (`_is_number`: bool/inf/nan/overflow → False), `:88-91` (confirmed_by_user обязателен), `:113-117` (min≤mode≤max), `:124-127` (≥2 варианта + статус-кво) |
| 10 | gov_head anchor + расщепление реестра приват/паблик | ✅ | `scripts/governance.py:120-133` (gov_heads.json трекается=шипуемое; gov_heads.local.json gitignored=приватные якоря), `:157-165` (`_is_private_key` роутит запись), `:242-260` (атомарная запись, TOFU-якорь) |
| 11 | Decision-router правило присутствует в INSTRUCTIONS | ✅ | `scripts/mcp_server.py:1698-1719` (правило 2 «МАРШРУТ РЕШЕНИЯ» — гейт-маршрутизатор ДО прозы, анти-анкоринг мнения хоста, граница «решение vs справка») |
| 12 | Верхний слой калькулятора: `run_calculation` считает только код | ✅ | INSTRUCTIONS правило 13 `:1812-1848` (validate→run детерминированно, `safe_expr` компиляция, few-shot-модели self-consistency-тестятся) |

**Severity: OK.** Все 12 инвариантов держатся. Ров не деградировал за арку Moat v2 / decision-calc / registry-split.

---

## 3. Файрвол приват/паблик (несущее свойство OSS)

Все проверки — **чисто**:

| Проверка | Результат |
|----------|-----------|
| Приватные имена в трекаемых **именах файлов** (каталоги из локального `advisors/*`) | НЕТ ✅ |
| Приватные имена в **теле** трекаемых файлов (`git grep -li`) | НЕТ ✅ |
| Секреты `sk-or-v1-` в трекаемых файлах | НЕТ ✅ |
| `.env` трекается | НЕТ ✅ |
| Сырые копирайт-исходники (`reference-library-raw/`) трекаются | НЕТ ✅ |
| `advisors/*` трекается | только `advisors/README.md` ✅ |
| `gov_heads.json` трекаемый = **только** `lenses/strategist` (n=31), приватных якорей нет | ✅ (`git show HEAD:gov_heads.json`) |
| `.gitignore` покрывает advisors/*, reference-library-raw/, *-raw/, gov_heads.local.json, principis.md, relationship.md, board_config.json, scripts/golden/, mcp.json, .env | ✅ (все строки на месте) |

**Что реально шипуется** (fresh clone видит): `lenses/strategist/{corpus.jsonl,lens.md,corpus.lock.json,sources/manifest.json}`,
пять `lenses/*.md` (cfo/marketer/sales/mckinsey-strategy/strategist), `advisors/README.md`, `gov_heads.json`, весь `scripts/`, SKILL.md, docs.
Приватные советники (собранные локально из чужих корпусов) **и** PD-советники (machiavelli/marcus-aurelius/sun-tzu) равно gitignored под `advisors/*` — в паблик едет **только линза «Стратег»**.

### Предлагаемый ритуал «firewall-check» (по образцу moat-check)

Один pre-push греп по **трекаемым** файлам — падает, если приватное имя/секрет просочилось в индекс. Держать как
`scripts/firewall_check.sh` + git pre-push hook (или Makefile-таргет). Псевдо-реализация:

```sh
#!/bin/sh
# firewall_check.sh — БЛОКИРУЕТ push, если приватные данные попали в трекаемые git-файлы.
# Имена приватных советников НЕ хардкодятся: выводятся из локального (gitignored) advisors/,
# чтобы сам скрипт не носил реальных имён живых людей в публичный репозиторий.
# Скрипт исключает себя из скана, иначе его собственные паттерны дадут ложный FAIL.
set -e
self='scripts/firewall_check.sh'
fail=0
# PD-фигуры — их имена легитимно стоят в трекаемых доках/тестах. Остальное в advisors/ = приватное
# (fail-closed: новый советник запрещён в git, пока имя не внесено в PD-allowlist).
PD_ALLOW='machiavelli|marcus-aurelius|sun-tzu|epictetus|seneca|aristotle'
# Список приватных имён = каталоги в advisors/ минус README минус PD-allowlist.
PRIV=$(ls advisors 2>/dev/null | grep -v '^README.md$' | grep -ivE "^($PD_ALLOW)$" | paste -sd'|' -)
# 1. приватные имена в именах ИЛИ теле трекаемых файлов (если локально есть советники)
if [ -n "$PRIV" ]; then
  if git ls-files | grep -iE "$PRIV"; then echo "FAIL: приватное имя в имени трекаемого файла"; fail=1; fi
  if git grep -liE "$PRIV" -- . ":!$self"; then echo "FAIL: приватное имя в теле трекаемого файла"; fail=1; fi
fi
# 2. секреты — паттерн ловит РЕАЛЬНЫЙ ключ (префикс+хвост), не голый префикс из доков
if git grep -lE 'sk-or-v1-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}' -- . ":!$self"; then echo "FAIL: похоже на секрет"; fail=1; fi
# 3. файлы, которые НИКОГДА не должны трекаться
for f in .env gov_heads.local.json principis.md relationship.md board_config.json; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then echo "FAIL: $f трекается"; fail=1; fi
done
if git ls-files | grep -E '^advisors/' | grep -qv '^advisors/README.md'; then echo "FAIL: advisors/* трекается"; fail=1; fi
if git ls-files | grep -Eq 'reference-library-raw/|-raw/'; then echo "FAIL: сырьё-raw трекается"; fail=1; fi
# 4. gov_heads.json содержит только шипуемые ключи (lenses/*), не advisors/*
if git show HEAD:gov_heads.json | grep -q '"advisors/'; then echo "FAIL: приватный якорь в трекаемом реестре"; fail=1; fi
[ "$fail" = 0 ] && echo "firewall-check: OK" || exit 1
```

**Severity: OK сейчас, но LOW-риск без автоматизации** — ритуал ручной; один неудачный `git add -A` во время работы
с приватными советниками пробьёт файрвол. Скрипт+hook закрывают человеческую ошибку. **Рекомендация: добавить до флипа.**

---

## 4. Структурное здоровье кода

- **Крупнейшие файлы (кандидаты на split):**
  - `scripts/mcp_server.py` — **1899 строк** (в ~4× больше следующего). Несёт 37 тулов + INSTRUCTIONS + JSON-RPC-транспорт +
    two-phase протокол. Читается, но это God-file. **Рекомендация (не блокер): вынести `INSTRUCTIONS` + `_FEWSHOT_*` в
    отдельный `instructions.py`, host-judge-протокол (`_host_judgment_phase1`/`_gate_verdict`/audit) в `host_judge.py`.**
  - Далее `eval.py` 610, `session_render.py` 507 — в норме.
- **TODO/FIXME по существу:** всего 2 в трекаемом коде, оба некритичные —
  `scripts/exp_graph.py:12` (переписать валидацию на enrichment-рёбра) и `scripts/ingest_telegram.py:10` (нет пагинации истории).
  Ни одного FIXME/HACK/долга в горячем пути рва.
- **Half-wired / «тёмные» тулы (MEDIUM).** 37 тулов зарегистрированы и покрыты тестами, но **10 из них не упомянуты в
  INSTRUCTIONS и не вынесены в `recipes.json`** — значит хост (Claude) не имеет правила их вызвать, и для внешнего юзера
  они недостижимы: `capture_situation`, `situation_analyze`, `situation_stress_test` (движок «ситуационная карта»),
  `calibrate`, `mirror_report`, `atomic_grounding`, `advisor_weights`, `stability`, плюс служебные `ollama_ensure`,
  `validate_manifest`, `job_status`, `scaffold_principis`. Служебные (job_status/validate_manifest/ollama_ensure) —
  ожидаемо внутренние. Но **ситуационная карта и calibrate/mirror/stability — это фичи с тестами, которые «горят вхолостую»**:
  код есть, проводки к хосту нет. Либо провести в INSTRUCTIONS/recipes, либо явно пометить как internal/CLI-only.
  Доказательство: сверка `mcp_server.list_tools()` × `INSTRUCTIONS` (10 тулов «OUT»), и `grep` по `recipes.json@HEAD` → 0 упоминаний.
- **Орфанов/мёртвого кода не найдено** — все тулы имеют handler; все «OUT»-тулы имеют тесты (`test_mirror.py`,
  `test_stability.py`, `test_atomic.py`, `test_extractor.py` и т.д.), т.е. это не dead code, а недо-экспонированные фичи.
- **Незакоммиченная правка в рабочем дереве:** `recipes.json` (M) — заменяет триггер `"Мангер против Naval"` →
  `"Макиавелли против Сунь-цзы"`. Это **улучшение консистентности** (Munger/Naval не входят в паблик-набор), но правка
  висит незакоммиченной. **Рекомендация: закоммитить отдельно от этого аудита.**

---

## 5. Public-readiness scorecard

| Артефакт | Статус | Замечание |
|----------|--------|-----------|
| LICENSE | ✅ | MIT, полный текст, © 2026 Ilya Autov (`LICENSE:1-3`) |
| README.md | ✅ | Точен; пути (`council/sessions/`, `SKILL.md`) существуют; приватных имён нет |
| QUICKSTART.md | ✅ | Три пути установки; все команды `board.py` (doctor/seed-council/recipes/build-advisor/setup-full) реально существуют |
| CONNECT-MCP.md | ✅ | `mcp-install`/`mcp-config` существуют; cwd/абс-пути и приват-граница описаны верно |
| install.py | ✅ | `RUNTIME` шипует `lenses` + `gov_heads.json`; сохраняет user-data (advisors/*, board_config, golden, data); пере-запуск безопасен; ставит **рабочую линзу «Стратег»** (corpus.jsonl 31 P1-чанк, Giles 1910 PD) |
| doctor офлайн | ✅ | Прогон без ollama/движка → «✅ здоров», exit 0; селф-тест контура `✓ дословный→🔵, фейк→fail-closed` проходит |
| Fresh-install даёт рабочий совет | ✅ (с оговоркой) | Линза «Стратег» = Сунь-цзы едет и работает лексически. Стартовый PD-совет (`seed-council`: Аврелий+Эпиктет) требует сетевой сборки корпусов (collect_pd) — норм, но это не «из коробки офлайн» |

**Косметическая несостыковка (MEDIUM):** INSTRUCTIONS (`:1737` пример «Макиавелли → Аврелий») и `recipes.json`
(`seed-council` предлагает «Аврелий + Эпиктет»; триггеры «добавить Мангера», «Мангер против Naval») ссылаются на
советников, которых **в fresh clone нет** (едет только линза «Стратег»). Свежий юзер, попросивший «Макиавелли против
Сунь-цзы», получит только Сунь-цзы (через линзу) — Макиавелли не соберётся без сетевого билда. Приватности это не нарушает
(все имена — публичные мыслители), но обещание не совпадает с поставкой. Рабочая правка `recipes.json` (§4) закрывает часть.

---

## 6. Известные отложенные пункты — текущий статус

| Пункт | Статус | Доказательство |
|-------|--------|----------------|
| Инфляция «мотивированного хоста» (~24% потолок), ollama-ре-аудит | ⚠️ **Частично / измерение отложено** | Статические измерения есть: `scripts/atomic.py:44-50` (`inflation_gap`), `scripts/poison_eval.py:12-60`. Адверсариальный dev-эксперимент (эмуляция хоста, знающего про гейт, через OpenRouter) — **не построен**, помечен «ОСТАТОК» в `docs/dev/2026-07-02-moat-v2-roadmap.md:48,58`. Числа ~24% в коде нет |
| Phase-1 farming-by-rephrase — измерить | ❌ **Не построено** | Ни в `docs/dev/`, ни в `scripts/`, ни в `tests/` нет eval на farming перефразом. Roadmap Phase-1 (1.1–1.4) этого пункта не содержит |
| `config_set` value-domain | ❌ **Открыто (LOW blast-radius)** | `scripts/mcp_server.py:569-584`: проверяется только КЛЮЧ (warning на неизвестный, `:582`), значение пишется без валидации типа/диапазона. Downstream смягчает: `relevance_gate.py:103-106` коэрсит битые значения fail-closed при чтении → мусор дефолтится, а не роняет гейт |
| sun-tzu golden coverage | ⚠️ **Частично** | Retrieval-golden есть (`scripts/golden/sun-tzu.retrieval.en.jsonl`, gitignored под `scripts/golden/`); **answerable-golden нет** → sun-tzu не в moat-батарее (`docs/dev/2026-07-02-moat-v2-roadmap.md:127`). Machiavelli/Marcus имеют оба |
| Back-boundary edge cases / apparatus #55 | ✅ **Реализовано и покрыто** | `scripts/corpusbuild/apparatus.py:11-18` (#55 документирован), `:236-310` (host-gated back-slice, fail-open к `needs_host_review`); тесты `tests/test_apparatus.py:203,220-260,333+` (реальный Giles-кейс, обе ветки #55) |

Прочие открытые доки в `docs/dev/`: `2026-07-03-decision-map-mc-design.md` — дизайн-спека (реализация MC частично идёт),
`2026-06-30-lenses-over-personalities.md` — направление (не блокер), `2026-06-30-zero-code-edit-audit.md` — открытый вопрос
про Cowork→ollama мост (без резолюции).

---

## 7. Находки по severity

**CRITICAL:** нет.

**HIGH**
- **H1 — Ключ OpenRouter в `.env` (операционный, вне git).** `.env` gitignored и не трекается (файрвол чист), но ключ
  существует на диске и, по памяти проекта, использовался. **Перед публикацией — ротировать** (даже при отсутствии в
  истории: история уже вычищена ранее, но живой ключ на машине = гигиена). Не код-блокер, но блокер флипа.

**MEDIUM**
- **M1 — «Тёмные» тулы без проводки в INSTRUCTIONS/recipes** (§4): ситуационная карта (`capture_situation`/`situation_analyze`/
  `situation_stress_test`), `calibrate`, `mirror_report`, `atomic_grounding`, `advisor_weights`, `stability` реализованы+протестированы,
  но недостижимы для хоста. Провести или пометить internal.
- **M2 — Примеры/рецепты ссылаются на не-шипуемых советников** (§5): INSTRUCTIONS/recipes зовут Макиавелли/Аврелий/Мангер/Naval,
  в fresh clone едет только линза «Стратег». Обещание ≠ поставка. Рабочая правка `recipes.json` частично закрывает.
- **M3 — `mcp_server.py` 1899 строк** (§4): God-file, кандидат на split (instructions/host-judge вынести). Тех-долг, не дефект.

**LOW**
- **L1 — firewall-check не автоматизирован** (§3): ритуал ручной; добавить `scripts/firewall_check.sh` + pre-push hook.
- **L2 — `config_set` без value-domain** (§6): blast-radius мал (downstream коэрсинг fail-closed), но тул принимает произвольные значения.
- **L3 — Незакоммиченная правка `recipes.json`** в рабочем дереве (§4): закоммитить отдельно.
- **L4 — sun-tzu answerable-golden отсутствует** (§6): moat-батарея не покрывает sun-tzu на answerable.

---

## 8. Итог: честный вердикт готовности + порядок оставшихся блокеров

**Вердикт: GO с оговорками.** Код готов — ров цел (12/12 инвариантов), файрвол чист, тесты зелёные офлайн, документация
точна, fresh-install даёт рабочую линзу. Ни одного код-блокера уровня CRITICAL/HIGH. Единственный HIGH — операционный.

**Порядок закрытия перед `public`:**
1. **[HIGH, вне кода]** Ротировать ключ OpenRouter в `.env`; подтвердить, что ключа нет в git-истории (`git log -p -S 'sk-or-v1-'`).
2. **[LOW→делать первым, дёшево]** Добавить `scripts/firewall_check.sh` + pre-push hook (§3) — механизирует несущее свойство.
3. **[MEDIUM]** Решить судьбу «тёмных» тулов (M1): либо провести ситуационную карту/calibrate/mirror в INSTRUCTIONS+recipes,
   либо явно пометить как internal (чтобы аудит не читал их как half-wired).
4. **[MEDIUM]** Причесать примеры под реальную поставку (M2): закоммитить правку `recipes.json`; выровнять INSTRUCTIONS-примеры/
   seed-council на то, что действительно едет (линза «Стратег» + сетевая PD-сборка Аврелия/Эпиктета описать как «соберётся»).
5. **[LOW, по желанию]** `config_set` value-domain (L2), sun-tzu answerable-golden (L4), split `mcp_server.py` (M3) — пост-релизно.

Пункты 3–5 — полировка впечатления и тех-долг, не безопасность. Безопасность и легальная граница закрыты **сейчас**.
