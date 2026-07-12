# Демо: офлайн заседание совета-федерации

Сессия `demo-session` — разнообразие: **full**, статус: завершено.

## Роли

### Марк Аврелий (Стоик) (`aurelius`)

**Представитель:** Действуй сейчас: единственное, чем ты владеешь, — это настоящее дело. Не откладывай.

- 🔵 «Confine thyself to the present.» — *Meditations 7.29 (Long)*

**Дивергенция:** 0.9394 (high ⚠ помечено)

**Модели-воркеры (3):** claude-sonnet-5, gemini-3-pro, gpt-5.2

**Заземлённых реплик:** 1/3

**Вердикт:** PASS

<details><summary>Все 3 реплики (сырые, не схлопнуты)</summary>

1. *(claude-sonnet-5)* Действуй сейчас: единственное, чем ты владеешь, — это настоящее дело. Не откладывай.
   - 🔵 «Confine thyself to the present.» — *Meditations 7.29 (Long)*
2. *(gemini-3-pro)* Прежде чем действовать, проверь: это в твоей власти изменить, или ты тревожишься о чужом?
   - 🟡 «This precise sentence was never written by any advisor in this corpus.»
3. *(gpt-5.2)* Сама постановка вопроса ошибочна — спокойствие не результат действия, а взгляд на него.
   - 🟡 «This precise sentence was never written by any advisor in this corpus.»

</details>

### Макиавелли (`machiavelli`)

**Представитель:** Действуй решительно: колебание читается слабостью, а слабость приглашает удар.

- 🔵 «It is much safer to be feared than loved.» — *The Prince, ch. 17*

**Дивергенция:** 0.9727 (high ⚠ помечено)

**Модели-воркеры (3):** claude-sonnet-5, gemini-3-pro, gpt-5.2

**Заземлённых реплик:** 1/3

**Вердикт:** PASS

<details><summary>Все 3 реплики (сырые, не схлопнуты)</summary>

1. *(claude-sonnet-5)* Действуй решительно: колебание читается слабостью, а слабость приглашает удар.
   - 🔵 «It is much safer to be feared than loved.» — *The Prince, ch. 17*
2. *(gemini-3-pro)* Не спеши — сначала выясни, на чьей стороне реальная сила, потом выбирай ход.
   - 🟡 «This precise sentence was never written by any advisor in this corpus.»
3. *(gpt-5.2)* Вопрос не в том, действовать ли, а в том, кто понесёт цену ошибки — раздели риск заранее.
   - 🟡 «This precise sentence was never written by any advisor in this corpus.»

</details>

## Что показывает демо

Это плюмбинг ОДНОЙ машины: очередь (`federation/queue.py`) → исполнитель (`federation/executor.py`, реальные `claim_brief`/`submit_candidate`) → координатор (`federation/coordinator.py`) → **реальный** гейт верности (`mcp_server._fidelity_check` против настоящего корпуса, не мок) → рендер. Это НЕ доказательство кросс-модельного разнообразия: в этом демо ВСЕ кандидаты написаны хостом и лишь ПОМЕЧЕНЫ разными worker_model — сами тексты аргументов не порождены независимыми LLM. Что доказано по-настоящему: гейт дискриминирует (сфабрикованная цитата остаётся 🟡, дословная — 🔵), сырые реплики сохраняются (не схлопываются в best-of-N), дивергенция считается.
