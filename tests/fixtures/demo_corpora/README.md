# Демо-фикстуры корпусов (M7, CI)

Минимальные СИНТЕТИЧЕСКИЕ корпуса для демо-тестов (`tests/test_demo_scenarios.py`,
`tests/test_refusal_demo.py`). Реальные корпуса (`advisors/<slug>/build/corpus.jsonl`)
gitignored и в CI отсутствуют → без фикстуры ~16 демо-тестов молча скипались.

Как работает: conftest-фикстура `demo_pd_corpora` (session scope) копирует `<slug>.jsonl`
в `advisors/<slug>/build/corpus.jsonl`, ТОЛЬКО если реальный корпус не собран; после сьюта
созданное прибирается. Локально (реальный корпус есть) — no-op, демо гоняется по живому
корпусу, как раньше.

Содержимое: короткие public-domain строки (Meditations, пер. George Long 1862; The Prince) —
ровно те, что демо-сценарии сверяют живым гейтом верности. Только PD-фигуры, никаких
приватных слагов. `advisors/*` gitignored → FS-песочница материализацию не видит.
