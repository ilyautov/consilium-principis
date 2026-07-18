# tests/fixtures/scores/ — замороженные скоры для offline regression-гейта

Слой 2 узла 2 (спека 2026-07-18). Продюсер этих фикстур — refresh-ритуал владельца на
semantic-машине (см. `docs/dev/retrieval-regression-refresh.md`), НЕ CI: живые скоры движка
замораживаются здесь, а блокирующий гейт (`scripts/retrieval_regression.py`) гоняет по ним
ЧИСТУЮ математику метрик без сети на каждый PR.

Имя файла: `<slug>.<backend>.json` (напр. `machiavelli.semantic.json`). Backend в имени — числа
движко-зависимы, semantic ≠ lexical сравнивать нельзя.

Продюсер — `python3 scripts/eval.py advisors/<slug> --engine semantic --emit-scores <файл>`
(тот же движок, что и baseline). Пересобрал корпус → пересними и baseline, и фикстуру одним
прогоном, иначе `corpus_sha256` разойдётся и гейт честно упадёт (baseline stale).

Схема (см. докстринг `retrieval_regression.metrics_from_frozen`):

```json
{
  "meta": {"ts": "<UTC>", "backend": "semantic"},
  "advisors": {
    "<slug>": {
      "corpus_sha256": "<full-sha256>",
      "ooc_scores": [0.02, 0.05, "…max-скор ретрива по каждому OOC-вопросу"],
      "ans_scores": [0.61, 0.72, "…max-скор по каждому answerable-вопросу"],
      "retrieval": {
        "ru": {"hit1": [true, false, "…"], "hit3": [true, true, "…"], "degenerate": false},
        "en": {"hit1": ["…"], "hit3": ["…"]}
      }
    }
  }
}
```

`degenerate: true` на страте → гейт её ПРОПУСКАЕТ (кросс-язык на lexical даёт недостоверные
числа). В каталоге лежат реальные semantic-фикстуры 3 PD-советников (machiavelli, marcus-aurelius,
sun-tzu), снятые на ollama+bge-m3; `test_committed_real_fixtures_pass_gate` гоняет по ним гейт на
каждый PR. Математику гейта дополнительно покрывает `tests/test_retrieval_regression.py`
синтетическими фикстурами (offline, без движка).
