#!/usr/bin/env python3
"""
board_init.py — авто-настройка скилла при старте: выбор tier ретрива на советника.

Две версии (решение Ильи): SIMPLE (без инфры) и FULL (семантический стек: ollama + bge-m3).
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.lexical import LexicalEngine
from corpusbuild.paths import corpus_path
from file_atomic import atomic_write_json

# Ключи, которые board_init ПЕРЕСЧИТЫВАЕТ при каждом запуске (машинные факты о доске).
# Всё остальное в board_config.json — пользовательские настройки (config_set: abstain_threshold,
# hybrid_alpha, retrieval_mode, language, interface_mode, …) и chunk_chars, под который уже
# нарезан корпус, — СОХРАНЯЕТСЯ. Ревью (security M2): install.py обещал «board_config.json не
# затирается переустановкой», а board_init писал файл с нуля → каждое обновление скилла молча
# сбрасывало порог воздержания и прочий тюнинг.
RECOMPUTED_KEYS = ("semantic_available", "token_threshold", "advisors")


def load_existing_config(path):
    """Текущий board_config.json как dict; нет файла / битый JSON / не-объект → {} (fail-safe)."""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def merge_config(existing, computed, force_keys=()):
    """Слить пересчитанный конфиг с существующим: RECOMPUTED_KEYS и force_keys берутся из
    computed, остальные существующие ключи сохраняются, недостающие — дополняются из computed.
    abstain_threshold-словарь дополняется по тирам, заданные пользователем тиры не трогаются."""
    cfg = dict(existing)
    for k in (*RECOMPUTED_KEYS, *force_keys):
        if k in computed:
            cfg[k] = computed[k]
    for k, v in computed.items():
        cfg.setdefault(k, v)
    at, at_new = cfg.get("abstain_threshold"), computed.get("abstain_threshold")
    if isinstance(at, dict) and isinstance(at_new, dict) and "abstain_threshold" not in force_keys:
        cfg["abstain_threshold"] = {**at_new, **at}
    return cfg

def est_tokens_corpus(adv_dir):
    cj = corpus_path(adv_dir)
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
        content = f.read().lower()
    return "quote_bank" in content or "quote bank" in content

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
    # чистый зазор → 0% галлюцинаций И 0% ложных отказов). Прежний порог 0.62 давал 50% over-abstention.
    # PROVISIONAL: N=12 на одном советнике (marcus-aurelius), привязано к chunk-size (TIER_CHUNK_CHARS);
    # пересчитать на большом корпусе. Safety-биас вверх: галлюцинация опаснее ложного отказа.
    # default=None: отличаем ЯВНО заданный порог (перекрывает сохранённый) от дефолта (не трогает).
    ap.add_argument("--abstain-threshold", type=float, default=None)
    ap.add_argument("--reset", action="store_true",
                    help="собрать конфиг с нуля, отбросив пользовательские настройки")
    args = ap.parse_args()
    abstain_default = 0.50
    abstain = abstain_default if args.abstain_threshold is None else args.abstain_threshold

    sem = str(args.semantic_available).lower() in ("1", "true", "yes")
    root = args.advisors_root
    advisors = sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))

    print(f"Семантический бэкенд (bge-m3): {'ДОСТУПЕН' if sem else 'нет'}")
    print(f"Порог tier: {args.threshold} токенов · abstain_threshold: {abstain}\n")

    config = {"semantic_available": sem,
              # auto = semantic при доступном bge-m3, иначе lexical (graceful).
              # НЕ hybrid по умолчанию: живой замер 2026-06-29 показал, что RRF-гибрид СТРОГО ХУЖЕ
              # чистой семантики — кросс-язычный лексический шум равным рангом топит сигнал
              # (semantic 0.61 на верном пассаже → hybrid 0.03 с биографией наверху). Совпадает с
              # bridge-retrieval-falsified (Exp A N=100, McNemar c=0). hybrid остался opt-in (prefer).
              "retrieval_mode": "auto",
              "abstain_threshold": {
                  "semantic": abstain,                  # калиброван при chunk_chars ниже
                  "lexical": LexicalEngine.DEFAULT_THRESHOLD,  # лексический пол (best-effort)
              },
              "chunk_chars": int(os.getenv("TIER_CHUNK_CHARS", "500")),
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
    existing = {} if args.reset else load_existing_config(out)
    force = ("abstain_threshold",) if args.abstain_threshold is not None else ()
    merged = merge_config(existing, config, force_keys=force)
    kept = sorted(k for k in existing if k not in RECOMPUTED_KEYS and k not in force)
    atomic_write_json(out, merged)
    print(f"\nКонфиг записан: {out}" + (f" (сохранены настройки: {', '.join(kept)})" if kept else ""))
    print("Скилл будет грузить ретрив по tier каждого советника (адаптер backends).")

if __name__ == "__main__":
    main()
