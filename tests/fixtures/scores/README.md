# tests/fixtures/scores/ — замороженные скоры для offline regression-гейта

Слой 2 узла 2 (спека 2026-07-18). Продюсер этих фикстур — refresh-ритуал владельца на
semantic-машине (см. `docs/dev/retrieval-regression-refresh.md`), НЕ CI: живые скоры движка
замораживаются здесь, а блокирующий гейт (`scripts/retrieval_regression.py`) гоняет по ним
ЧИСТУЮ математику метрик без сети на каждый PR.

Имя файла: `<slug>.<backend>.json` (напр. `machiavelli.semantic.json`). Backend в имени — числа
движко-зависимы, semantic ≠ lexical сравнивать нельзя.

Схема (см. докстринг `retrieval_regression.metrics_from_frozen`):

```json
{
  "meta": {"corpus_sha256": {"<slug>": "<full-sha256>"}},
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
числа). Каталог намеренно без реальных фикстур: семантические скоры снимаются на машине с
ollama+bge-m3, не в оффлайн-CI. Математику гейта покрывает `tests/test_retrieval_regression.py`
синтетическими фикстурами.
