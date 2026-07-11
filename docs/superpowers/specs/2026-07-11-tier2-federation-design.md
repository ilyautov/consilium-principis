# Tier-2 Federation — Design Spec

**Дата:** 2026-07-11 · **Ветка:** `feat/tier2-federation` (создать от master) · **Статус:** апрув получен.

Многомозговый совет (northstar [[council-topology-northstar]]): персоны-советники разнесены по
разным моделям/эндпоинтам, чтобы честное разнообразие не было «persona-hats на одной модели»
(коррелированные ошибки). Координатор-клиент кладёт роль-таски в очередь; исполнители-клиенты
(другие сессии Claude Code/Codex/Gemini или API-воркеры) забирают, играют советника на СВОЕЙ
модели, кладут кандидата; best-of-N судья + централизованная верность → заседание.

**⚠ Эмпирический гейт (юзер оверрайднул секвенс осознанно 2026-07-11):** northstar-правило было
«строить Tier-2 только после того, как живой Tier-1 A/B докажет диверсити кросс-модели». Юзер
выбрал «строить всё сейчас, A/B как пост-валидация». Зафиксировано; строим. Живой кросс-модельный
прогон всё равно за ключом юзера — офлайн-каркас и контур строятся и тестируются без ключа.

## Инварианты (жёсткие)

- **Fail-closed контур НЕ ослабляем.** Роль не заполнена за timeout → деградация (host single-brain
  для этой роли или воздержание), НИКОГДА не выдумываем.
- **Централизованная верность.** Исполнитель отдаёт кандидат-текст + предлагаемые цитаты; 🔵 ставит
  ТОЛЬКО наш сервер, прогнав каждую цитату через `_fidelity_check` по корпусу советника. Воркер НЕ
  самосертифицирует 🔵 — моат не размазывается по чужим клиентам.
- **Приватность.** Стейт-файл несёт вопрос юзера → `.consilium/` gitignored, никогда не шипится
  (инвариант как у `council/`). Тулы федерации не читают `council/`/`decisions/`/`principis.md`.
- **ToS дизайном:** personal / attended / себе-в-пользу. Без пула аккаунтов, single-machine дефолт.

## Ключевые инженерные решения (из 2 раундов ресёрча)

- **Дефолт-бэкенд = SQLite** (stdlib `sqlite3` + WAL + `BEGIN IMMEDIATE` + `busy_timeout`), НЕ файловая
  очередь на `os.rename` (проигрывает по failure-mode при той же нулевой зависимости) и НЕ Redis
  (демон+порт=инфра; для соло «без Docker» — нельзя). SQLite: ноль демонов/портов, один файл, airgap.
- **`QueueBackend` ABC — шов.** `claim(worker_id, roles, block, timeout)` заложен С БЛОКИРОВКОЙ сразу:
  для SQLite это внутренний sleep-poll, при подмене на `RedisBackend`/`HttpBackend`/`PostgresBackend`
  (team/corp) `block=True` становится pass-through к нативному `BLPOP`/subscribe — «разблокируется
  бесплатно», код вызывающих не меняется. Зеркалит DBOS (SQLite локально → Postgres в проде, тот же API).
- **Гонки claim нет** — single-writer SQLite сериализует. `UPDATE…RETURNING` (SQLite ≥3.35) с
  рантайм-фолбэком на SELECT+UPDATE (паттерн `litequeue`), CAS по rowcount==1.
- **Listen = гибрид notify+poll.** poll — источник истины (потолок гарантирует доставку); notify —
  только акселерант латентности, надёжным быть не обязан (потерянный звонок → poll подберёт).
- **MCP не умеет push** (SEP-1686) → воркеры на claim-цикле; идиома Claude Code Agent Teams (self-claim).

---

## Подсистемы

### ① Транспорт — `scripts/federation/queue.py`

`QueueBackend` ABC:
```
enqueue(task: RoleTask) -> task_id
claim(worker_id, roles=None, block=False, timeout=0.0) -> Task | None
ack(task_id, result: dict) -> None
nack(task_id, error: str) -> None          # -> dead-letter состояние
heartbeat(task_id, worker_id) -> None      # обновить claimed_at (живость)
sweep(lease_seconds) -> int                # вернуть протухшие claim'ы в pending, вернуть кол-во
status(task_id | session_id) -> dict
```

`SqliteBackend(db_path)` — дефолт. Схема `tasks(id, session_id, role, advisor_dir, question,
status[pending|claimed|done|dead], claimed_by, claimed_at, result_json, error, created_at,
priority)`. WAL, `busy_timeout=5000`. Claim:
```sql
BEGIN IMMEDIATE;
UPDATE tasks SET status='claimed', claimed_by=?, claimed_at=?
WHERE id=(SELECT id FROM tasks WHERE status='pending'
          AND (:roles IS NULL OR role IN (:roles))
          ORDER BY priority, created_at LIMIT 1)
RETURNING *;
COMMIT;
```
Рантайм-проверка `sqlite3.sqlite_version_info >= (3,35,0)`; иначе SELECT-id → UPDATE…WHERE
id=? AND status='pending' в той же транзакции, rowcount==1 = успех. `data_version` (PRAGMA) —
дешёвый пред-чек «что-то менялось» перед полным claim-запросом на непронотификанных пробуждениях.
Стейт-файл: `.consilium/federation.sqlite3` (создаётся в корне доски; `.consilium/` в `.gitignore`).

### ② Listen-loop + notify — `scripts/federation/notify.py`

`claim(block=True, timeout=N)` внутри SqliteBackend:
```
deadline = now + timeout
loop:
    t = _claim_once(worker_id, roles)     # BEGIN IMMEDIATE claim
    if t: return t
    if now >= deadline: return None
    notifier.wait(min(deadline-now, backoff))   # backoff: full-jitter 0.5s→cap 5s
```
`Notifier` интерфейс: `notify()` / `wait(timeout)`.
- `FifoNotifier` (POSIX дефолт): FIFO в `.consilium/federation.wake`; `wait` = `select([fd], timeout)`
  (мгновенное пробуждение на запись); `notify` = неблокирующая запись байта (EAGAIN/no-reader
  игнорируется — потеря допустима). `enqueue()` вызывает `notifier.notify()`.
- `PollNotifier` (Windows/фолбэк): `wait(timeout)` = `time.sleep(timeout)`; `notify()` = no-op.
- Выбор: FIFO если `hasattr(os,'mkfifo')` и создание удалось, иначе PollNotifier (fail-safe).
Full-jitter backoff (`random.uniform(0, min(cap, base*2^n))`) гасит thundering-herd `SQLITE_BUSY`
у N простаивающих воркеров. Сброс backoff в базу на любой активности.

**Heartbeat/reclaim:** воркер зовёт `heartbeat(task_id)` периодически; `sweep(lease)` (зовёт любой
активный воркер или координатор на poll) возвращает `claimed AND claimed_at < now-lease` в pending.
Lease по длительности таска (дефолт 120с, конфиг).

### ③ Координатор — тулы в `scripts/mcp_server.py` (+ логика в `scripts/federation/coordinator.py`)

- `federation_open(question, roles[], best_of=1, backend="sqlite")` → создаёт session_id, кладёт
  роль-таски (по роли × best_of). `roles[]` = список `{role, advisor_dir}`. Возвращает {session_id,
  enqueued}. МУТИРУЮЩИЙ по смыслу, но локальный стейт — не гейтим правилом 0 (не сеть, не публикация).
- `federation_poll(session_id)` → {roles: [{role, got, needed}], done: bool, candidates_summary}.
- `federation_assemble(session_id, lease=120)` → для каждой роли: (1) `sweep` протухших; (2) best-of-N
  судья по рубрике на собранных кандидатах; (3) **централизованная верность**: каждую предложенную
  цитату победителя гоним через `_fidelity_check` — не 🔵 P1/P2 → цитата понижается/снимается; (4)
  сборка session-объекта (advisors/opinions/disagreement/synthesis) → передаётся в `render_session`.
  **Fail-closed:** роль без кандидатов после sweep → degrade-политика {host_single_brain | abstain}
  (дефолт abstain с честной пометкой «роль не заполнена федерацией»).

**Судья-рубрика** (переиспользуем relevance_gate v2 / judge_backend, детерминизм где можно):
цитирует корпус? держит линзу советника? возражает по существу (не поддакивает)? — скор на кандидата,
победитель = макс. Ноль LLM-судьи в MVP-каркасе (rule-based по наличию верифиц. цитат + длине/фокусу);
LLM-судья — за флагом, требует ключ (как cite host-judge). Каркас fail-closed без ключа.

### ④ Исполнитель — тулы в `scripts/mcp_server.py`

- `federation_claim(worker_id, roles?, block=true, timeout=2.0, backend="sqlite")` → claim роль-таск →
  `{task_id, role, advisor_dir, question}` либо `{empty:true}` по таймауту.
- `federation_submit(task_id, worker_id, candidate)` → `candidate={argument, quotes:[{text}], ...}`
  кладётся в result. Верность НЕ проверяется здесь (централизованно на assemble) — но кладём как есть.
- `federation_heartbeat(task_id, worker_id)` → живость.
Исполнитель-цикл = блок в INSTRUCTIONS: «вступил воркером → federation_claim(block) → сыграй роль
советника (advisor_dir) на СВОЕЙ модели, цитаты бери из cite → federation_submit → повтор; стоп по
флагу/пустому запросу юзера». Тихая оркестрация (Rule 1) сохранена.

### ⑤ Док — `docs/FEDERATION.md`

Personal/attended/себе-в-пользу прямым текстом: «твои подписки для твоих решений, не бэкенд для
сервиса»; single-machine дефолт; как открыть исполнителя во 2-й сессии; когда апгрейдить бэкенд
(team/corp → Redis/HTTP за тем же ABC); приватность стейта.

---

## Тестирование (офлайн, `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=…`)

- **queue:** enqueue/claim/ack/nack/status; гонка N потоков→claim ровно один (single-writer);
  sweep возвращает протухший claim; RETURNING-фолбэк (мок версии <3.35); dead-letter на nack.
- **notify:** `block=True` возвращает по появлению таска БЫСТРЕЕ poll-потолка (notify-путь); потерянный
  звонок → таск доставлен в пределах ceiling (poll-бэкстоп); форс `PollNotifier` доставляет sleep-poll;
  N воркеров на одном звонке → claim ровно один.
- **coordinator:** open→poll→assemble на mock-кандидатах; best-of-N выбирает по рубрике; централизованная
  верность понижает фейк-🔵; fail-closed (роль пуста после sweep → degrade abstain).
- **executor:** claim/submit/heartbeat круг; claim пустой по таймауту → {empty}.
- selfdoc-regen при новых тест-файлах; гард тёмных тулов (новые federation_*-тулы засветить в
  INSTRUCTIONS исполнитель-циклом + описаниями).

## Границы (out of scope MVP)

- Кросс-машинность / `RedisBackend`/`HttpBackend`/`PostgresBackend` — дизайн-шов готов, реализация
  за пределами MVP (team/corp тир).
- LLM-судья — за флагом+ключом; MVP-каркас rule-based.
- Живой кросс-модельный A/B — за ключом юзера (пост-валидация, как Tier-1 probe).
- Отдельный executor-бинарь — MVP = INSTRUCTIONS-цикл.

Связано: [[council-topology-northstar]], [[moat-legible-branch]], [[competitive-landscape-2026-07]],
[[situational-map-and-mcp]].
