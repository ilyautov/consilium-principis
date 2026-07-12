# Ритуалы заседания совета — дизайн (4 режима из ресёрча)

> Спека 2026-07-12. Из дип-ресёрча `docs/dev/research-advisory-boards-2026-07.md`. Ветка `feat/tier2-federation` (firewall: не мержить/пушить автономно). Строить последовательно (делят mcp_server/INSTRUCTIONS/recipes/selfdoc). B гейтит C.

## Контекст (что уже есть — НЕ строить)
Режим B (живой круглый стол, Rule 4), Debate (`clash-two`), Panel (`full-council`), `premortem`-тул (ЧИСЛОВОЙ прогон сценариев ≠ фасилитаторский), `advisor_weights`/`loop_status`/`ledger` (петля исхода U1), `_disagreement` в рендере, федерация `divergence`. Скаффолд A/B — `scripts/experiments/antisycophancy_probe.py` (bootstrap-CI, compare, judge по осям 0-3/3.0). Рендер — `scripts/session_render.py`.

## Инвариант рва (все 4): не ослаблять fail-closed. Тиры верности (🔵/🟢/🟡) текут сквозь любой новый вывод; 🔵 только от гейта; воздержание видимо.

---

## A. Decision-record — протокол заседания как ВЫХОД совета
**Что:** канонический структурированный вывод сессии (перенос Diligent Smart Minutes + red-team decision-record, arXiv 2607.01913). Даёт память совета (пробел) и питает петлю исхода U1 (запись = то, что `advisor_weights` позже разрешает по факту).

**Форма записи** (детерминированно из session-объекта, ноль LLM):
```
{question, options:[{label, assumptions:[{text, tier}], risk?}], dissent:[{advisor, position}],
 decision:{choice, rationale, status: approve|approve_with_conditions|defer|redesign|reject},
 re_review_triggers:[...], provenance:{blue, green, yellow, abstained}}
```
- `assumptions[].tier` = тир верности (🔵/🟢/🟡) — сам протокол помечен provenance.
- `dissent` — из `_disagreement(session)` (Режим B) ИЛИ федеративной `divergence` (реплики не схлопнуты).
- `provenance` — счётчики маркеров по сессии (сколько заземлено vs воздержано).

**Файлы:** `scripts/decision_record.py` (builder `build_record(session)` — pure) + `render_decision_record(record, surface=md)` в `session_render.py` + тул `decision_record` в `mcp_server` (handler → builder+render) + INSTRUCTIONS-упоминание (write? нет — read-only агрегат сессии, тихо Rule 1) + recipe `decision-record` + гард тёмных тулов.
**Тесты:** builder на mock-сессии (тиры текут, dissent из disagreement, статусы решения); фейк-🔵 в assumption НЕ поднимается (тир берётся из session-маркера, не выдумывается); пустая сессия → честный skeleton, не краш. Enterprise-раздельность: минуты (эта запись) ≠ action-tracker (отдельно, за MVP).
**Риск:** низкий. Не зависит от догфуда.

## B. Devil's-advocate probe (СНАЧАЛА ИЗМЕРИТЬ, потом режим)
**Что:** изолированный A/B — двигает ли СТРУКТУРНЫЙ (роле-мандатный) адвокат дьявола выходы LLM, там где мягкий нудж дал НОЛЬ ([[antisycophancy-phase1-negative]]). Эмпирика AMJ (DI/DA > консенсус) — на людях; на LLM непроверено. Честная методология: probe → (если эффект есть) режим.

**Файлы:** `scripts/experiments/devils_advocate_probe.py` — ЗЕРКАЛИТ `antisycophancy_probe.py`: `run(condition, battery, call)`, условия `baseline` (обычный синтез) vs `devils_advocate` (одна роль СТРУКТУРНО назначена атаковать складывающийся консенсус — не текст-нудж, а роль в протоколе), `judge_response` по осям (`assumptions_surfaced`, `risks_named`, `conclusion_changed`), `_bootstrap_ci`, `compare`. Батарея решений-сценариев (мини, в репо). 0 правок INSTRUCTIONS. Результат в `scripts/experiments/results/`.
**Тесты:** offline-детерминизм на mock-call (SEED-пин, как у antisycophancy); compare даёт CI; ноль-сеть в CI.
**Риск:** нулевой для продукта (эксперимент). ГЕЙТИТ C: эффект в CI → строим DA/Delphi-режим; ноль → C переосмыслить/не шиппить как «работает».

## C. NGT/Delphi анонимные независимые раунды (ГЕЙТ: результат B)
**Что:** советники генерят НЕЗАВИСИМО до взаимодействия (NGT silent generation), потом сходятся; идентичность анонимизирована (снижает модель-к-модели конформизм). Валидировано arXiv 2601.19921 (диверсити несёт). На один мозг — последовательные независимые проходы БЕЗ видимости чужих ответов в контексте; на федерацию — очередь уже изолирует роли (переиспользовать `divergence`/`assemble`).
**Файлы (ЕСЛИ B зелёный):** `scripts/deliberation_rounds.py` (independent-gen → converge-report, переиспользует федеративную `divergence`) + INSTRUCTIONS-режим (round-протокол) + recipe `delphi`/`ngt` + гард.
**Тесты:** независимость (проход N не видит проход M), convergence/divergence-репорт, анонимизация. 
**Риск:** средний; ГЕЙТ на B (не строить полный режим, если структурный DA не двигает выходы — иначе театр, повтор ошибки «Tier-2 до A/B-гейта»).

## D. Позиционирование (docs, не код, не README)
**Что:** внутренняя записка отстройки + внешняя валидация рва.
**Файлы:** `docs/dev/positioning-vs-competitors.md` — строка «verified board, not chatbot cosplay» (provenance vs breadth); внешняя валидация структурного разногласия (AMJ 10.5465/255859, Klein pre-mortem, arXiv 2601.19921); cautionary «Historical Figures» (Rolling Stone) ЗА fail-closed; этика digital-twin (consent/provenance-заявление даже на PD; граница 🟡 vs «слова в уста мёртвого»). **НЕ на публичный README** до догфуда федерации (diversity-оверклейм). Гард `test_readme_honest_claims` не трогаем.
**Риск:** нулевой (docs).

---

## Секвенс сборки
D (docs, изолирован) → B (probe, изолирован) → **читаю результат B** → A (decision-record, независим — строю в любом случае) → C (только если B зелёный). Каждый TDD, offline-CI, selfdoc-regen при новых тест-файлах, коммит на ветку. Адверсариальное ревью на A (тиры верности в протоколе — фейк-🔵 не поднять).

Связано: [[advisory-boards-research-2026-07]], [[antisycophancy-phase1-negative]], [[tier2-federation-shipped]], [[council-topology-northstar]].
