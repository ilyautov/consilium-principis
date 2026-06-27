#!/usr/bin/env python3
"""Governance-субстрат (Барсик-примитив для Consilium): hash-chain провенанс + promote-gate.

Барсик = «Git для живой памяти»: память юзера/советника экстернализуется ПОД управлением.
Контур уже даёт тир по манифесту (engine/provenance.py), но тир там — статичный конфиг.
Этот модуль добавляет две вещи, которых не хватало:

  1. HASH-CHAIN — провенанс как tamper-evident леджер: каждая запись хешируется вместе с
     хешем предыдущей (как блоки git/блокчейна). Подмена текста ПОСЛЕ факта рвёт цепочку
     и ловится verify_chain. Нужно для Принцепса: факты/решения юзера должны быть
     неизменяемо-зафиксированы, а не переписываемы задним числом.

  2. PROMOTE-GATE — повышение тира (рост доверия, A→S→P) проходит гейт с ДОКАЗАТЕЛЬСТВОМ.
     Нельзя просто пометить запись P1; повышение требует evidence (ссылка на манифест/
     источник). Нет доказательства → отказ, остаёшься на текущем тире (fail-closed).
     Понижение (падение доверия) разрешено всегда — это безопасная сторона.

Тир-порядок согласован с engine/fidelity (0 = самый авторитетный). Неизвестный тир →
наименее авторитетный (fail-closed: к нему повышать не нужно доказательств, ОТ него — нужно).
"""
import hashlib
import json

# 0 = самый авторитетный (дословные слова автора); A = апокриф/неустановленное.
TIER_ORDER = {"P1": 0, "P2": 1, "S1": 2, "S2": 3, "B": 4, "A": 5}
_UNKNOWN = 999  # неизвестный тир трактуем как наименее авторитетный

GENESIS = "GENESIS"


def _canonical(record):
    """Стабильная сериализация записи для хеша (порядок ключей фиксирован)."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


def record_hash(record, prev_hash):
    """sha256(prev_hash + canonical(record)) — связывает запись с предыдущей."""
    payload = (prev_hash + "\n" + _canonical(record)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_chain(records, genesis=GENESIS):
    """Список записей → леджер [{record, prev, hash}], каждая ссылается на хеш предыдущей."""
    chain = []
    prev = genesis
    for r in records:
        h = record_hash(r, prev)
        chain.append({"record": r, "prev": prev, "hash": h})
        prev = h
    return chain


def verify_chain(chain, genesis=GENESIS):
    """Проверка целостности. Возвращает (ok, broken_index): индекс ПЕРВОЙ записи, чей хеш
    или ссылка-на-предыдущую не сходятся (None, если цепочка чистая)."""
    prev = genesis
    for i, link in enumerate(chain):
        if link["prev"] != prev:
            return False, i
        if record_hash(link["record"], prev) != link["hash"]:
            return False, i
        prev = link["hash"]
    return True, None


def _rank(tier):
    return TIER_ORDER.get(tier, _UNKNOWN)


def promote_gate(current_tier, requested_tier, evidence=None):
    """Гейт смены тира. Возвращает ГРАНТНУТЫЙ тир.

    requested авторитетнее current (меньший ранг) = ПОВЫШЕНИЕ → нужен evidence (truthy),
    иначе отказ (остаёмся на current, fail-closed). Понижение/равенство — разрешено всегда.
    """
    if _rank(requested_tier) < _rank(current_tier):     # запрошено повышение доверия
        if evidence:
            return requested_tier
        return current_tier                              # нет доказательства → отказ
    return requested_tier                                # понижение или то же — ок


def _verify_corpus(corpus_jsonl):
    """CLI: построить цепочку над corpus.jsonl, проверить целостность, дать голову-хеш +
    гистограмму тиров. Голова-хеш = «отпечаток» корпуса: меняется при любой подмене."""
    import os
    if not os.path.isfile(corpus_jsonl):
        return None
    records, tiers = [], {}
    for line in open(corpus_jsonl, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        records.append(r)
        tiers[r.get("tier", "?")] = tiers.get(r.get("tier", "?"), 0) + 1
    chain = build_chain(records)
    ok, broken = verify_chain(chain)
    head = chain[-1]["hash"] if chain else GENESIS
    return {"n": len(records), "ok": ok, "broken": broken,
            "head": head, "tiers": tiers}


if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 3 or sys.argv[1] != "verify":
        print("Использование: python governance.py verify <dir | путь.jsonl>")
        sys.exit(1)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from corpusbuild.paths import corpus_path        # резолвер (build/ → legacy), не литерал
    target = sys.argv[2]
    cj = target if target.endswith(".jsonl") else corpus_path(target)
    res = _verify_corpus(cj)
    if res is None:
        print(f"[governance] нет corpus.jsonl: {cj}")
        sys.exit(1)
    status = "✅ целостна" if res["ok"] else f"❌ ПОДМЕНА на записи #{res['broken']}"
    tiers = " ".join(f"{k}:{v}" for k, v in sorted(res["tiers"].items()))
    print(f"[governance] {cj}")
    print(f"  записей {res['n']} · цепочка {status} · тиры [{tiers}]")
    print(f"  голова-хеш (отпечаток корпуса): {res['head'][:16]}…")
