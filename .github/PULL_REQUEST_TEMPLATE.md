<!-- Thanks for contributing! Fill in briefly and run through the checklist. Details in CONTRIBUTING.en.md. -->
<!-- Спасибо за вклад! Заполните коротко и пройдитесь по чек-листу. Детали — в CONTRIBUTING.md. -->

## What and why / Что и зачем

<!-- 1-3 sentences: what changes and which problem it solves. / что меняется и какую проблему решает. -->

## How verified / Как проверено

<!-- Commands/tests. The offline suite is mandatory: / Команды/тесты. Оффлайн-сьют обязателен: -->
<!-- OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q -->

## Checklist / Чек-лист

- [ ] No copyrighted text; no personal data (`advisors/`, `council/`, `.env`, `*.local.json`) in the diff
      · Ноль копирайтных текстов; ноль личных данных в diff
- [ ] `make test` green offline (except the env-fragile `test_ssrf_check_passes_public_blocks_private`)
      · `make test` зелёный офлайн (кроме env-хрупкого теста SSRF)
- [ ] New behavior is covered by a test written BEFORE the implementation (TDD)
      · Новое поведение покрыто тестом, написанным ДО реализации (TDD)
- [ ] If the fidelity gate / abstention was touched — a test proves honesty did not weaken (fail-closed)
      · Если тронут гейт верности / abstention — есть тест, что честность не ослабла
- [ ] Selfdoc regenerated if tools/rules/tests changed (`gen_selfdoc.py` + `build_manual.py`)
      · Selfdoc перегенерирован, если менялись тулы/правила/тесты
- [ ] No secrets in the commits or history · В коммитах и истории нет секретов
