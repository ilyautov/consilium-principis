#!/usr/bin/env python3
"""LLM-as-judge релевантности: заменяет сломанный exact-anchor в retrieval eval.

Проблема: текущий retrieval eval ищет точную подстроку golden-якоря (5-7 слов)
в 500-символьных чанках — даёт 0% top-1 даже при работающем семантическом ретриве.
Решение: LLM-judge с рубрикой 0-3 вместо substring-match.

Экспортирует:
  judge(query, passage, model=None) -> int {0,1,2,3}
  retrieval_eval_judged(advisor_dir, golden, ...) -> dict
  main() — CLI поверх реального ретрива + golden
"""
import os
import sys
import math
import re

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import llm_local

# Детерминированный рубричный промпт — минимально вариативный, числовой вывод.
_JUDGE_PROMPT = """\
Оцени релевантность ПАССАЖА к ВОПРОСУ по шкале:
0 = нерелевантно: пассаж не связан с вопросом
1 = косвенно: пассаж касается смежной темы, но не отвечает на вопрос
2 = релевантно: пассаж частично отвечает на вопрос или даёт полезный контекст
3 = прямой ответ: пассаж прямо и полно отвечает на вопрос

ВОПРОС: {query}

ПАССАЖ: {passage}

Ответь ТОЛЬКО одной цифрой: 0, 1, 2 или 3. Никакого другого текста."""


def judge(query: str, passage: str, model=None) -> int:
    """Оценивает релевантность passage к query.

    Возвращает int ∈ {0,1,2,3}.
    FAIL-CLOSED: если ответ модели не содержит валидной цифры → 0.
    Никогда не завышаем (непарсируемое = нерелевантное).
    """
    prompt = _JUDGE_PROMPT.format(query=query, passage=passage)
    response = llm_local.generate(prompt, model=model, temperature=0.1)
    m = re.search(r"[0-3]", response)
    return int(m.group(0)) if m else 0  # FAIL-CLOSED


def _dcg(rels):
    """DCG = Σ rel_i / log2(i+2), i=0..k-1."""
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def _ndcg(rels):
    """nDCG = DCG / IDCG; IDCG = DCG rels отсортированных по убыванию. 0 если IDCG=0."""
    dcg = _dcg(rels)
    idcg = _dcg(sorted(rels, reverse=True))
    return dcg / idcg if idcg > 0 else 0.0


def retrieval_eval_judged(advisor_dir, golden, top_k=3, rel_threshold=2, retrieve_fn=None):
    """Retrieval eval через LLM-judge вместо exact-anchor.

    Args:
        advisor_dir: путь к папке советника
        golden: список {"q":..., "anchor":..., "ref":...}
        top_k: кол-во пассажей на вопрос
        rel_threshold: минимальный score для «попадания» (hit/precision)
        retrieve_fn: callable(query, advisor_dir, top_k) -> [{text, score, source}]
                     TEST SEAM — в тестах подаётся заглушка, в prod = eval.retrieve

    Returns:
        {
          "n": N,
          "hit_at_k": float,      # доля вопросов с хотя бы одним rel >= threshold
          "precision_at_k": float, # средняя доля топ-k пассажей rel >= threshold
          "ndcg_at_k": float,      # средний nDCG@k (стандарт: DCG/IDCG)
          "per_query": [...]
        }
    """
    if retrieve_fn is None:
        from eval import retrieve as _retrieve
        retrieve_fn = _retrieve

    per_query = []
    for row in golden:
        q = row["q"]
        passages = retrieve_fn(q, advisor_dir, top_k)
        rels = [judge(q, p["text"]) for p in passages]

        # Дополняем нулями если движок вернул меньше top_k пассажей
        while len(rels) < top_k:
            rels.append(0)
        rels = rels[:top_k]

        hit = int(any(r >= rel_threshold for r in rels))
        precision = sum(1 for r in rels if r >= rel_threshold) / len(rels) if rels else 0.0
        ndcg = _ndcg(rels)

        per_query.append({
            "q": q,
            "ref": row.get("ref", ""),
            "rels": rels,
            "hit_at_k": hit,
            "precision_at_k": round(precision, 4),
            "ndcg_at_k": round(ndcg, 4),
        })

    n = len(per_query)
    if n == 0:
        return {"n": 0, "hit_at_k": 0.0, "precision_at_k": 0.0, "ndcg_at_k": 0.0, "per_query": []}

    return {
        "n": n,
        "hit_at_k": round(sum(r["hit_at_k"] for r in per_query) / n, 4),
        "precision_at_k": round(sum(r["precision_at_k"] for r in per_query) / n, 4),
        "ndcg_at_k": round(sum(r["ndcg_at_k"] for r in per_query) / n, 4),
        "per_query": per_query,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="LLM-as-judge retrieval eval: precision@k / nDCG@k вместо exact-anchor"
    )
    ap.add_argument("advisors", nargs="*", help="папки советников (advisors/machiavelli …)")
    ap.add_argument("--top-k", type=int, default=3, help="кол-во пассажей (по умолч. 3)")
    ap.add_argument("--threshold", type=int, default=2,
                    help="минимальный judge-score для «попадания» (по умолч. 2)")
    ap.add_argument("--model", default=None, help="модель ollama (по умолч. из KERNEL_MODEL)")
    args = ap.parse_args()

    if not llm_local.available():
        print("Семантический/LLM бэкенд недоступен: ollama не отвечает — LLM-judge недоступен.")
        print("Запустите: ollama serve  (и убедитесь, что модель загружена)")
        sys.exit(1)

    from eval import retrieve as _retrieve, load_golden

    paths = args.advisors or []
    if not paths:
        print("Укажи папки советников: python relevance_judge.py advisors/machiavelli …",
              file=sys.stderr)
        sys.exit(1)

    for adv_dir in paths:
        name = os.path.basename(adv_dir.rstrip("/"))
        golden, path = load_golden(name, "retrieval")
        if not golden:
            print(f"  {name}: golden не найдено (scripts/golden/{name}.retrieval.jsonl)")
            continue

        print(f"\n=== {name}: LLM-judge retrieval eval "
              f"(top_k={args.top_k}, threshold={args.threshold}) ===")
        print(f"  Golden: {path}")

        result = retrieval_eval_judged(
            adv_dir, golden,
            top_k=args.top_k,
            rel_threshold=args.threshold,
            retrieve_fn=lambda q, d, k: _retrieve(q, d, top_k=k),
        )

        print(f"  n={result['n']}  "
              f"hit@{args.top_k}={result['hit_at_k']:.3f}  "
              f"precision@{args.top_k}={result['precision_at_k']:.3f}  "
              f"nDCG@{args.top_k}={result['ndcg_at_k']:.3f}")

        for row in result["per_query"]:
            mark = "✓" if row["hit_at_k"] else "✗"
            print(f"    {mark} rels={row['rels']}  "
                  f"prec={row['precision_at_k']}  nDCG={row['ndcg_at_k']}  "
                  f"[{row['ref']}] «{row['q'][:52]}»")


if __name__ == "__main__":
    main()
