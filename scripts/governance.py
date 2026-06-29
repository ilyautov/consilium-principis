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


def _lock_head(lock_json):
    """gov_head из build.lock.json (эталонный отпечаток корпуса), или None если нет."""
    import os
    if not os.path.isfile(lock_json):
        return None
    try:
        return json.load(open(lock_json, encoding="utf-8")).get("gov_head")
    except Exception:
        return None


def _verify_corpus(corpus_jsonl, expected_head=None):
    """Построить цепочку над corpus.jsonl, проверить целостность, дать голову-хеш + гистограмму
    тиров. Если передан expected_head (сохранённый в build.lock при сборке) — СВЕРИТЬ с ним:
    несовпадение = подмена corpus.jsonl ПОСЛЕ сборки (раньше цепь сверялась сама с собой —
    тавтология, ничего не ловила). head_match=None, если эталонной головы нет."""
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
    head_match = None if expected_head is None else (head == expected_head)
    return {"n": len(records), "ok": ok and head_match is not False, "broken": broken,
            "head": head, "expected_head": expected_head, "head_match": head_match,
            "tampered": head_match is False, "tiers": tiers}


if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 3 or sys.argv[1] != "verify":
        print("Использование: python governance.py verify <dir | путь.jsonl>")
        sys.exit(1)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from corpusbuild.paths import corpus_path, lock_path  # резолверы, не литералы
    target = sys.argv[2]
    cj = target if target.endswith(".jsonl") else corpus_path(target)
    expected = _lock_head(lock_path(target)) if not target.endswith(".jsonl") else None
    res = _verify_corpus(cj, expected_head=expected)
    if res is None:
        print(f"[governance] нет corpus.jsonl: {cj}")
        sys.exit(1)
    if res["tampered"]:
        status = "❌ ПОДМЕНА: голова ≠ build.lock"
    elif not res["ok"]:
        status = f"❌ ПОДМЕНА на записи #{res['broken']}"
    elif res["head_match"]:
        status = "✅ целостна (сверена с build.lock)"
    else:
        status = "✅ цепь консистентна (нет эталона в lock — собери заново для сверки)"
    tiers = " ".join(f"{k}:{v}" for k, v in sorted(res["tiers"].items()))
    print(f"[governance] {cj}")
    print(f"  записей {res['n']} · {status} · тиры [{tiers}]")
    print(f"  голова-хеш (отпечаток корпуса): {res['head'][:16]}…")
