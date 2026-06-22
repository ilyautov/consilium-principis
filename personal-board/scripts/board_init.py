#!/usr/bin/env python3
"""
board_init.py — авто-настройка скилла при старте: выбор tier ретрива на советника.

Две версии (решение Ильи): SIMPLE (без инфры) и FULL (семантический стек, как Гефест).
Скилл сам выбирает при старте по двум сигналам:
  - размер корпуса советника (этот скрипт считает);
  - доступность семантического бэкенда (агент проверяет ollama_health и передаёт флагом).

TIER SIMPLE  — full-context + лексический ретрив + exact-match гейт цитат. Нулевая инфра.
               Достаточно когда корпус мал (Via Negativa: не тащить вектор-БД ради неё).
TIER FULL    — bge-m3 эмбеддинги (ollama) + abstention threshold + опц. кросс-энкодер реранк
               + grounded-генерация. Нужен когда корпус большой И бэкенд доступен.

Использование (агент вызывает после ollama_health):
  python board_init.py advisors --semantic-available true --threshold 150000
"""
import sys, os, json, argparse, re

def est_tokens_corpus(adv_dir):
    cj = os.path.join(adv_dir, "corpus.jsonl")
    if not os.path.isfile(cj):
        return 0, 0
    chars, chunks = 0, 0
    with open(cj, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                chars += len(obj.get("text", ""))
                chunks += 1
            except Exception:
                pass
    return chars, chunks

def has_quote_bank(adv_dir):
    pm = os.path.join(adv_dir, "persona.md")
    if not os.path.isfile(pm):
        return False
    with open(pm, encoding="utf-8") as f:
        return "quote_bank" in f.read().lower() or "quote bank" in f.read().lower()

def decide(tokens, semantic_available, threshold):
    if tokens >= threshold and semantic_available:
        return "FULL", "большой корпус + семантика доступна"
    if tokens >= threshold and not semantic_available:
        return "SIMPLE", "🚩 большой корпус, но семантики нет — точность просядет, подключи ollama bge-m3"
    return "SIMPLE", "корпус мал — семантика избыточна (Via Negativa)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisors_root")
    ap.add_argument("--semantic-available", default="false")
    ap.add_argument("--threshold", type=int, default=150000)  # токенов
    # 0.50 — калибровано на корпусе советника (eval.py: вне-корпуса max 0.402, в-корпусе min 0.532;
    # чистый зазор → 0% галлюцинаций И 0% ложных отказов). Гефестовы 0.62 давали 50% over-abstention.
    # PROVISIONAL: N=12 на одном советнике (marcus-aurelius), привязано к chunk-size (TIER_CHUNK_CHARS);
    # пересчитать на большом корпусе. Safety-биас вверх: галлюцинация опаснее ложного отказа.
    ap.add_argument("--abstain-threshold", type=float, default=0.50)
    args = ap.parse_args()

    sem = str(args.semantic_available).lower() in ("1", "true", "yes")
    root = args.advisors_root
    advisors = sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))

    print(f"Семантический бэкенд (bge-m3): {'ДОСТУПЕН' if sem else 'нет'}")
    print(f"Порог tier: {args.threshold} токенов · abstain_threshold: {args.abstain_threshold}\n")

    config = {"semantic_available": sem, "abstain_threshold": args.abstain_threshold,
              "token_threshold": args.threshold, "advisors": {}}

    print(f"{'советник':<22}{'токены':>9}{'чанки':>7}  tier   причина")
    print("-" * 78)
    for name in advisors:
        adv = os.path.join(root, name)
        chars, chunks = est_tokens_corpus(adv)
        tokens = chars // 4
        tier, why = decide(tokens, sem, args.threshold)
        src = "корпус" if chunks else ("quote_bank" if has_quote_bank(adv) else "пусто")
        config["advisors"][name] = {"tokens": tokens, "chunks": chunks, "tier": tier, "source": src}
        print(f"{name:<22}{tokens:>9}{chunks:>7}  {tier:<6} {why}")

    out = os.path.join(os.path.dirname(root.rstrip('/')) or '.', "board_config.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"\nКонфиг записан: {out}")
    print("Скилл будет грузить ретрив по tier каждого советника (адаптер backends, как Гефест).")

if __name__ == "__main__":
    main()
