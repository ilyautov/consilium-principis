# Tier-2 Federation — Design Spec (v2, полн. ревизия)

**Дата:** 2026-07-11 · **Ветка:** `feat/tier2-federation` · **Статус:** апрув + критический пасс сложён.

Многомозговый совет (northstar [[council-topology-northstar]]): персоны разнесены по разным
моделям, чтобы разнообразие не было «persona-hats на одной модели» (коррелированные ошибки).
Координатор кладёт роль-таски в очередь; исполнители (другие сессии Claude Code/Codex/Gemini или
API-воркеры) забирают, играют советника на СВОЕЙ модели, кладут кандидата; агрегация с сохранением
дивергенции + централизованная верность → заседание.

**⚠ Эмпирический гейт (юзер оверрайднул секвенс осознанно):** northstar-правило было «Tier-2 только
после того, как живой Tier-1 A/B докажет диверсити». Юзер выбрал «строить всё сейчас, A/B —
пост-валидация». Зафиксировано. Живой кросс-модельный прогон за ключом юзера; каркас/контур
строятся и тестируются офлайн.

## Декомпозиция на 2 суб-проекта (2 плана)

- **Часть A — субстрат очереди** (`scripts/federation/`): domain-agnostic. QueueBackend ABC +
  SqliteBackend + notify + listen + heartbeat/sweep/retry. Свой план, самостоятельно тестируем.
- **Часть B — совет-федерация поверх субстрата**: координатор/исполнитель/агрегатор/верность/
  дивергенция/degrade/док. Свой план. Строится ПОСЛЕ части A.

## Инварианты (жёсткие)

- **Fail-closed НЕ ослабляем.** Роль не заполнена за timeout → degrade-политика (ниже), НИКОГДА не выдумываем.
- **Централизованная верность.** Исполнитель отдаёт кандидат-текст + предлагаемые цитаты; 🔵 ставит
  ТОЛЬКО наш сервер, прогнав каждую цитату через `_fidelity_check`. Воркер НЕ самосертифицирует 🔵.
- **Приватность.** Стейт-файл несёт вопрос юзера → `.consilium/` gitignored, не шипится. Тулы федерации
  не читают `council/`/`decisions/`/`principis.md`.
- **Trust-boundary исполнителя (улучш. 4):** модель доверия = «свои сессии» (personal/attended). Проза
  советника (`argument`) НЕ верифицируется корпусом (верны только цитаты) → воркер может прислать
  любой текст. Поэтому: (a) прямым текстом в доке «исполнители = твои доверенные сессии, не чужие»;
  (b) координатор валидирует submit (лимит размера, типы str, strip control-chars — как захардили
  export_session); (c) `argument` в выводе честно помечен «сгенерировано моделью-исполнителем».
- **ToS дизайном:** personal / attended / себе-в-пользу. Без пула аккаунтов, single-machine дефолт.

## Ключевые инженерные решения (2 раунда ресёрча)

- **Дефолт-бэкенд = SQLite** (stdlib `sqlite3` + WAL + `BEGIN IMMEDIATE` + `busy_timeout`), НЕ файловая
  очередь на `os.rename`, НЕ Redis (демон+порт=инфра; соло «без Docker» нельзя).
- **`QueueBackend` ABC — шов.** `claim(worker_id, roles, block, timeout)` С БЛОКИРОВКОЙ сразу: для
  SQLite = внутренний sleep-poll; подмена на Redis/HTTP/Postgres (team/corp) → `block=True` = pass-through
  к нативному `BLPOP`/subscribe («разблокируется бесплатно»). Зеркалит DBOS.
- **Гонки claim нет** — single-writer SQLite сериализует. `UPDATE…RETURNING` (≥3.35) с рантайм-фолбэком
  на SELECT+UPDATE (`litequeue`), CAS по rowcount==1.
- **Listen = гибрид notify+poll.** poll — истина; notify — акселерант (потерянный звонок → poll подберёт).
- **MCP не push** (SEP-1686) → воркеры на claim-цикле; идиома Claude Code Agent Teams (self-claim).

---

# Часть A — субстрат очереди (`scripts/federation/queue.py`, `notify.py`)

### QueueBackend ABC
```
enqueue(task: RoleTask) -> task_id
claim(worker_id, roles=None, block=False, timeout=0.0) -> Claim | None   # Claim несёт claim_token
ack(task_id, worker_id, claim_token, result: dict) -> {ok|stale}         # idempotent (улучш. 3)
nack(task_id, worker_id, claim_token, error: str) -> {ok|stale|dead}     # retry-кап (улучш. 7)
heartbeat(task_id, worker_id, claim_token) -> {ok|stale}
sweep(lease_seconds) -> int          # протухшие claim → pending (или dead при исчерпании retry)
status(task_id | session_id) -> dict
```

### SqliteBackend(db_path)
Схема `tasks(id, session_id, role, advisor_dir, question, status[pending|claimed|done|dead],
claimed_by, claim_token, claimed_at, attempts, max_attempts, result_json, error, created_at, priority)`.
WAL, `busy_timeout=5000`. Стейт `.consilium/federation.sqlite3` (корень доски; `.consilium/` в gitignore).

**Claim** (BEGIN IMMEDIATE; при claim'е генерим НОВЫЙ `claim_token` = uuid4 и `attempts += 1`):
```sql
UPDATE tasks SET status='claimed', claimed_by=?, claim_token=?, claimed_at=?, attempts=attempts+1
WHERE id=(SELECT id FROM tasks WHERE status='pending' AND (:roles IS NULL OR role IN (:roles))
          ORDER BY priority, created_at LIMIT 1)
RETURNING *;
```
Рантайм-проверка `sqlite3.sqlite_version_info >= (3,35,0)`; иначе SELECT-id→UPDATE…WHERE id=? AND
status='pending' в той же транзакции, rowcount==1. `data_version` (PRAGMA) — дешёвый пред-чек.

**Idempotent ack/nack/heartbeat (улучш. 3, закрывает stale-submit при reclaim/ABA):** валидны ТОЛЬКО
если `status=='claimed' AND claim_token==переданный`. Иначе → `{stale:true}` (таск реклеймлен/переназначен;
поздний ответ мёртвого воркера отбрасывается, дубликата/порчи нет). ack пишет result+status='done'.

**Retry-кап (улучш. 7):** `nack` и `sweep`-реклейм инкрементят на пути повторной раздачи; при
`attempts >= max_attempts` (дефолт 3) → `status='dead'` (dead-letter), координатору видно как «роль
провалилась K раз» — не бесконечный цикл на битом advisor_dir.

**Sweep:** `claimed AND claimed_at < now-lease` → если `attempts < max_attempts`: `pending`
(claim_token обнуляется — старый воркер станет stale); иначе `dead`. Возвращает кол-во.

### Notify — `notify.py`
`Notifier`: `notify()` / `wait(timeout)`.
- `FifoNotifier` (POSIX дефолт): FIFO `.consilium/federation.wake`; `wait`=`select([fd],timeout)`
  (мгновенно на запись); `notify`=неблокирующая запись байта (no-reader/EAGAIN игнор — потеря ок).
- `PollNotifier` (Windows/фолбэк): `wait`=`time.sleep(timeout)`, `notify`=no-op.
- Выбор: FIFO если `hasattr(os,'mkfifo')` и создание удалось, иначе PollNotifier (fail-safe).
`claim(block,timeout)` внутри: `{claim_once; успех→вернуть; иначе notifier.wait(min(остаток,backoff));
повтор}`. Full-jitter backoff `random.uniform(0,min(cap5s, base0.5s*2^n))` (гасит thundering-herd
`SQLITE_BUSY`), сброс на активности. `enqueue()` дёргает `notify()`.

### Тесты части A (офлайн)
- enqueue/claim/ack/nack/status; **гонка N НЕЗАВИСИМЫХ ПРОЦЕССОВ** (улучш. 6: `multiprocessing`/
  subprocess, не потоки — реальный file-lock) → claim ровно один на таск.
- **idempotent (улучш. 3):** stale ack/nack/heartbeat (чужой/старый claim_token) → `{stale}`, result
  не перезаписан; ABA (тот же воркер реклеймит после sweep, старый token) → старый submit stale.
- **retry-кап (улучш. 7):** nack×max_attempts → dead; sweep протухшего с исчерпанным retry → dead.
- sweep возвращает протухший claim в pending; RETURNING-фолбэк (мок версии <3.35).
- **notify:** `block=True` возвращает по появлению БЫСТРЕЕ poll-потолка; потерянный звонок → доставка
  в пределах ceiling (poll-бэкстоп); форс `PollNotifier` доставляет sleep-poll; N воркеров на 1 звонке → один claim.

---

# Часть B — совет-федерация поверх субстрата

### Модель агрегации (улучш. 1 — НЕ схлопывать разнообразие)

Две РАЗНЫЕ оси, обрабатываются по-разному:
- **Разные персоны (роли)** → их несогласие = совет, СОХРАНЯЕМ (судья между Аврелием и Макиавелли
  не выбирает — это и есть продукт). Каждая роль → своё мнение в заседании.
- **Одна персона × N моделей** (`replicas` на роль, бывший best_of) → НЕ «судья выбрал 1, остальное
  выкинул». Вместо: (a) выбираем рубрикой лучший ВОЛОС-репрезентант для рендера; (b) считаем и
  прикрепляем **`divergence`** — сошлись ли N моделей (та же стойка? те же цитаты?). Сошлись → сигнал
  высокой уверенности; разошлись → флаг «даже кросс-модельно эта персона раскололась». Разнообразие
  становится КАЛИБРОВОЧНЫМ сигналом, а не выкинутым мусором. Поле `divergence` в выводе assemble.

### Идентичность модели (улучш. 2 — иначе премиса непроверяема)
`federation_submit(..., worker_model)` — само-репорт модели исполнителя. Хранится в result; assemble
показывает «Аврелий (via Opus) vs (via GPT)» и считает `divergence` ИМЕННО поперёк моделей. Без этого
нельзя отличить настоящий кросс-модель от N копий одной модели (и A/B нефальсифицируем).

### Координатор — тулы (логика в `scripts/federation/coordinator.py`)
- `federation_open(question, roles[], replicas=1, degrade="host_single_brain")` → session_id + роль-таски
  (по роли × replicas). `roles[]`=`{role, advisor_dir}`.
- `federation_poll(session_id)` → {roles:[{role, got, needed, models[]}], done, dead[]}. Оппортунистич.
  `sweep` на каждом poll.
- `federation_assemble(session_id, lease=120)` → per роль: sweep → если replicas>1 посчитать
  divergence поперёк моделей + выбрать рубрикой репрезентанта → **централизованная верность** (каждую
  цитату через `_fidelity_check`, не 🔵 P1/P2 → понизить/снять) → валидация+лейбл `argument` → сборка
  session-объекта (advisors/opinions/divergence/disagreement/synthesis) → `render_session`.

**degrade (улучш. 5), per-роль, ЛЕЙБЛИРОВАННО:** роль без кандидатов после sweep →
- `host_single_brain` (ДЕФОЛТ): координатор-хост играет роль сам, помечено «на координатор-модели,
  не федеративно» + флаг `diversity: reduced`. Юзер получает ответ, честность держит лейбл.
- `abstain` (опция): роль честно пуста «не заполнена федерацией».
Никогда не выдумываем скрытно (fail-closed сохранён — деградация ВИДИМА).

**Судья-рубрика** (rule-based MVP, переиспуем relevance_gate v2): цитирует корпус? держит линзу?
возражает по существу? — скор на кандидат. LLM-судья за флагом+ключом. Каркас fail-closed без ключа.

### Исполнитель — тулы
- `federation_claim(worker_id, roles?, block=true, timeout=2.0)` → `{task_id, claim_token, role,
  advisor_dir, question}` либо `{empty:true}` по таймауту.
- `federation_submit(task_id, worker_id, claim_token, worker_model, candidate)` → валидация (размер/
  типы/control-chars), затем `ack` с claim_token (stale → отклонён). `candidate={argument, quotes:[{text}]}`.
- `federation_heartbeat(task_id, worker_id, claim_token)`.
Цикл = INSTRUCTIONS-блок: «вступил воркером → federation_claim(block) → сыграй роль (advisor_dir) на
СВОЕЙ модели, цитаты из cite → federation_submit(worker_model=своя модель) → повтор; стоп по флагу».
Тихая оркестрация (Rule 1) сохранена. Новые federation_*-тулы засветить (гард тёмных тулов).

### Док — `docs/FEDERATION.md`
Personal/attended/себе-в-пользу: «твои подписки для твоих решений, не бэкенд для сервиса»;
исполнители = твои доверенные сессии; single-machine дефолт; как открыть воркера; когда апгрейдить
бэкенд (Redis/HTTP за ABC); приватность стейта; что divergence значит для читателя.

### Тесты части B (офлайн)
- coordinator open→poll→assemble на mock-кандидатах; **divergence (улучш. 1):** 3 согласных реплики →
  low divergence; разошедшиеся → high + флаг; репрезентант выбран рубрикой, но остальные НЕ потеряны.
- **model identity (улучш. 2):** assemble несёт per-реплика `worker_model`; divergence считается поперёк моделей.
- **централизованная верность:** фейк-🔵 от воркера → понижен; **argument-валидация (улучш. 4):** пере-размер/
  control-chars/не-str → отклонён/санитайзен, не крашит.
- **degrade (улучш. 5):** роль пуста → host_single_brain с лейблом + `diversity:reduced`; опция abstain → пусто.
- executor claim/submit(stale claim_token → отклонён)/heartbeat круг.

## Заимствования из awesome-llm-apps `advisor-orchestrator-worker` (2026-07-12)

Внешняя валидация: 118k★-репа независимо пришла к трёхуровневому скелету (оркестратор/воркер/
критик + централизованная верификация + stateless-брифы + честный бюджет). Совпадение шаблона
снимает риск «мы одни так думаем»; их гейт — по acceptance-criteria (качество), НЕ verbatim-верность
по PD-корпусу — наш ров цел. Три практических заимствования в Часть B:

1. **Worker-brief как temp-file, не shell-интерполяция** (их `references/worker-brief.md`): бриф
   исполнителю передаётся как self-contained данные, НИКОГДА не вклеивается в shell-строку —
   защита от инъекции/утечки контекста. Прямо усиливает trust-boundary исполнителя (улучш. 4):
   `federation_claim` отдаёт структурный `Claim`, не собираемую команду.
2. **Явные состояния судьи `PASS / FIX / ESCALATE`** (вместо неявных): FIX = редиспатч с названным
   провалом (наш `nack`→requeue с `error`), ESCALATE = честный отчёт/вопрос (наш degrade/abstain),
   «no silent partial passes». Завести именование в рубрику судьи Части B.
3. **Формат ответа критика** (их `references/advisor-consult.md`): «verdict, ranked risks, concrete
   fixes, <300 слов, только на границах коммита» — образец для нашего best-of-N судьи-рубрики.

## Границы (out of scope MVP)
- Кросс-машинность / Redis/HTTP/Postgres-бэкенды — шов готов, реализация за MVP (team/corp).
- LLM-судья — за флагом+ключом; MVP rule-based.
- Живой кросс-модельный A/B — за ключом юзера (пост-валидация).
- Отдельный executor-бинарь — MVP = INSTRUCTIONS-цикл.

Связано: [[council-topology-northstar]], [[moat-legible-branch]], [[competitive-landscape-2026-07]],
[[situational-map-and-mcp]].
