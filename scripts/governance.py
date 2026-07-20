#!/usr/bin/env python3
"""Governance-субстрат (Барсик-примитив для Consilium): hash-chain провенанс + promote-gate.

Барсик = «Git для живой памяти»: память юзера/советника экстернализуется ПОД управлением.
Контур уже даёт тир по манифесту (engine/provenance.py), но тир там — статичный конфиг.
Этот модуль добавляет две вещи, которых не хватало:

  1. HASH-CHAIN — провенанс как tamper-evident леджер: каждая запись хешируется вместе с
     хешем предыдущей (как блоки git/блокчейна). Подмена текста ПОСЛЕ факта рвёт цепочку
     и ловится verify_chain. Нужно для Принцепса: факты/решения юзера должны быть
     неизменяемо-зафиксированы, а не переписываемы задним числом.
     МОДЕЛЬ УГРОЗ (честно, без оверселла):
       • gov_head в build.lock ловит СЛУЧАЙНУЮ порчу / частичную подмену (правка corpus.jsonl
         без обновления lock);
       • ЯКОРЬ в gov_heads.json (корень доски, ВНЕ папки советника) ловит подмену советника
         ЦЕЛИКОМ по модели TRUST-ON-FIRST-USE: советника, собранного/замороженного ЛОКАЛЬНО,
         затем подменили целой чужой папкой (corpus.jsonl + самосогласованные lock'и) — голова
         не совпадёт с ранее записанным якорем. Это про пост-установочную подмену локального
         советника, НЕ про изначально вредоносную поставку.
       • ЧЕГО НЕ ловит: (а) СКАЧАННУЮ доску целиком — там противник контролирует и корень, и
         реестр (пришлёт согласованный gov_heads.json), TOFU-якоря нет; (б) противника с
         записью в корень уже-установленной доски (перепишет реестр); (в) отравленную
         ПЕРЕСБОРКУ через легитимный pipeline (её гейтят Rule 0 + гарды add_source): легит-
         сборка обновляет якорь по определению.
       • ЭТО СОВЕЩАТЕЛЬНАЯ (advisory) проверка, НЕ гейт на пути выдачи. _cite/_retrieve её НЕ
         зовут — тир/цитаты идут своим контуром (fidelity). Подмену показывает лишь явный
         вызов governance_verify / doctor; не полагайся на неё как на блокировку в рантайме.

  2. PROMOTE-GATE — повышение тира (рост доверия, A→S→P) проходит гейт с ДОКАЗАТЕЛЬСТВОМ.
     Нельзя просто пометить запись P1; повышение требует evidence (ссылка на манифест/
     источник). Нет доказательства → отказ, остаёшься на текущем тире (fail-closed).
     Понижение (падение доверия) разрешено всегда — это безопасная сторона.

Тир-порядок согласован с engine/fidelity (0 = самый авторитетный). Неизвестный тир →
наименее авторитетный (fail-closed: к нему повышать не нужно доказательств, ОТ него — нужно).
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    if not os.path.isfile(lock_json):
        return None
    try:
        return json.load(open(lock_json, encoding="utf-8")).get("gov_head")
    except Exception:
        return None


def expected_head_for(advisor_dir):
    """Эталонный gov_head советника: build.lock (локальная сборка) ИЛИ трекаемый corpus.lock.json
    (шипованный корпус — переживает клон). None, если ни одного нет."""
    from corpusbuild.paths import lock_path, head_lock_path
    return _lock_head(lock_path(advisor_dir)) or _lock_head(head_lock_path(advisor_dir))


# ─────────────────────────── ЯКОРЬ ВНЕ ПОДМЕНЯЕМОЙ ПАПКИ ───────────────────────────
# gov_heads.json в КОРНЕ доски: advisor→head. build.lock/corpus.lock живут ВНУТРИ папки
# советника и подменяются вместе с ней; якорь снаружи — единственная точка, которую
# «шипованный» (самосогласованный) советник-подкидыш не может унести с собой.

# РАЗДЕЛЕНИЕ ПО ШИПУЕМОСТИ (копирайт/приватность-файрвол): реестр расщеплён на два файла.
#   • gov_heads.json (ТРЕКАЕТСЯ git, едет в public-репо и install RUNTIME) — ТОЛЬКО шипуемое:
#     lenses/* (PD/CC-линзы). Их имена публичны по определению.
#   • gov_heads.local.json (GITIGNORED, per-user) — advisors/* = якоря приватных советников
#     (реальные живые люди). Имена НИКОГДА не должны попасть в git. Один `git add -A` над
#     трекаемым файлом не может утащить приватное — оно физически в другом, игнорируемом файле.
# Читатели (verify/doctor) берут ОБЪЕДИНЕНИЕ обоих (local дополняет/переопределяет tracked);
# writer маршрутизирует по ключу; лечение эвакуирует легаси-advisors/* из трекаемого файла.
REGISTRY_NAME = "gov_heads.json"
LOCAL_REGISTRY_NAME = "gov_heads.local.json"


def _registry_root(root=None):
    if root is not None:
        return root
    from corpusbuild.paths import project_root
    return project_root()


def registry_path(root=None):
    """Путь ТРЕКАЕМОГО реестра (шипуемое: lenses/*)."""
    return os.path.join(_registry_root(root), REGISTRY_NAME)


def local_registry_path(root=None):
    """Путь ЛОКАЛЬНОГО (gitignored) реестра приватных советников (advisors/*)."""
    return os.path.join(_registry_root(root), LOCAL_REGISTRY_NAME)


def _is_private_key(key):
    """Приватный ключ = советник (advisors/*): реальный живой человек, per-user, НЕ шипуется.
    Всё прочее (lenses/* и т.п.) — шипуемое, живёт в трекаемом реестре."""
    return isinstance(key, str) and key.startswith("advisors/")


def _registry_path_for_key(key, root=None):
    """Маршрут якоря по ключу: приватный → local (gitignored), шипуемый → tracked (git)."""
    return local_registry_path(root) if _is_private_key(key) else registry_path(root)


def _advisor_key(advisor_dir, root):
    """Ключ реестра = путь советника ОТНОСИТЕЛЬНО корня доски (forward-slash, кросс-платформенно).
    Советник вне корня (tmp/внешний каталог) → None: якорить нечем, реестр не трогаем."""
    rel = os.path.relpath(os.path.realpath(advisor_dir), os.path.realpath(root))
    if rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel):
        return None
    return rel.replace(os.sep, "/")


def _read_registry_file(path):
    """(status, dict) для ОДНОГО файла-реестра, status ∈ 'absent'|'ok'|'malformed'. БИТЫЙ ≠
    ОТСУТСТВУЮЩИЙ: truncated/невалидный JSON — это ПОРЧА (оборванная запись / подмена / внешняя
    порча), а НЕ «ещё не мигрировали». Отсутствие → мягкое предупреждение (миграция); порча →
    громкий провал (fail-closed) — иначе битый реестр молча отключал бы детект подмены."""
    if not os.path.isfile(path):
        return "absent", {}
    try:
        reg = json.load(open(path, encoding="utf-8"))
    except Exception:
        return "malformed", {}
    return ("ok", reg) if isinstance(reg, dict) else ("malformed", {})


def _read_registry(root=None):
    """ОБЪЕДИНЕНИЕ трекаемого (lenses/*) и локального (advisors/*) реестров, (status, dict).
    status='malformed', если ЛЮБОЙ из файлов битый (fail-closed для обоих); иначе 'ok', если
    хоть один присутствует; иначе 'absent'. local дополняет/переопределяет tracked (per-user
    поверх шипуемого). Побочно само-лечит легаси: эвакуирует advisors/* из трекаемого файла."""
    root = _registry_root(root)
    _heal_tracked_registry(root)
    ts, tracked = _read_registry_file(registry_path(root))
    ls, local = _read_registry_file(local_registry_path(root))
    if ts == "malformed" or ls == "malformed":
        return "malformed", {}
    merged = dict(tracked)
    merged.update(local)                                 # local поверх tracked
    if ts == "absent" and ls == "absent":
        return "absent", {}
    return "ok", merged


def _heal_tracked_registry(root=None):
    """Одноразовое само-лечение легаси/грязного состояния: если ТРЕКАЕМЫЙ gov_heads.json содержит
    приватные ключи (advisors/* — ровно текущее грязное рабочее дерево), эвакуировать их в local
    (gitignored) и переписать трекаемый БЕЗ них. Так пользователь с приватными записями в
    трекаемом файле автоматически получает их вынос, а public-репо остаётся чист от имён людей.
    Битый любой из файлов → no-op (порча — громкий провал в читателях, НЕ молчаливая миграция;
    не затираем битый файл). Идемпотентно: после первого прогона advisors/* в трекаемом нет."""
    root = _registry_root(root)
    ts, tracked = _read_registry_file(registry_path(root))
    if ts != "ok":
        return
    private = {k: v for k, v in tracked.items() if _is_private_key(k)}
    if not private:
        return                                           # чисто — нечего лечить
    ls, local = _read_registry_file(local_registry_path(root))
    if ls == "malformed":
        return                                           # не затираем битый local (fail-closed)
    for k, v in private.items():
        local.setdefault(k, v)                           # существующий local-якорь приоритетнее
    _atomic_write_json(local_registry_path(root), local)
    remaining = {k: v for k, v in tracked.items() if not _is_private_key(k)}
    _atomic_write_json(registry_path(root), remaining)   # трекаемый — только шипуемое


def load_registry(root=None):
    """Совместимость: dict-объединение (пустой при absent/malformed). Статусы — _read_registry."""
    return _read_registry(root)[1]


def _atomic_write_json(path, obj):
    """Атомарная запись: пишем во временный файл в ТОЙ ЖЕ директории, затем os.replace (атомарно
    на POSIX/Windows). Оборванная/конкурентная запись НЕ оставляет усечённый gov_heads.json —
    читатель видит либо старую, либо новую полную версию (закрывает и гонку параллельных сборок)."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".gov_heads.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def register_head(advisor_dir, head, n=None, root=None):
    """Зарегистрировать/обновить якорь советника в gov_heads.json (атомарно). Зовётся ТОЛЬКО
    легитимной сборкой (buildlock.write_lock) и владельческим freeze. Советник вне корня →
    None (no-op). Битый реестр пересобирается с этого ключа (само-лечение легит-сборкой)."""
    root = _registry_root(root)
    key = _advisor_key(advisor_dir, root)
    if key is None:
        return None
    target = _registry_path_for_key(key, root)           # advisors/* → local; lenses/* → tracked
    reg = _read_registry_file(target)[1]                 # битый целевой → {} → пересбор с этого ключа
    reg[key] = {"gov_head": head, "n": n}
    _atomic_write_json(target, reg)
    return {"path": target, "key": key, "gov_head": head}


def anchored_head_for(advisor_dir, root=None):
    """Якорная голова советника из gov_heads.json, или None (не зарегистрирован / нет / битый реестр)."""
    root = _registry_root(root)
    key = _advisor_key(advisor_dir, root)
    if key is None:
        return None
    status, reg = _read_registry(root)
    if status != "ok":
        return None
    entry = reg.get(key)
    return entry.get("gov_head") if isinstance(entry, dict) else None


def verify_advisor(advisor_dir, root=None):
    """Полная проверка советника: цепь + внутрипапочный эталон (build.lock/corpus.lock.json)
    + внешний якорь (gov_heads.json). Ключевой случай — ПОДМЕНА ЦЕЛИКОМ: вся папка заменена
    самосогласованным двойником → цепь сходится, внутренние lock'и сходятся, но голова ≠ якорю
    → swap_suspect=True, tampered=True (громкий вердикт). Якорь не зарегистрирован →
    anchor_registered=False (предупреждение, НЕ провал: миграция старых советников)."""
    from corpusbuild.paths import corpus_path
    res = _verify_corpus(corpus_path(advisor_dir), expected_head=expected_head_for(advisor_dir))
    if res is None:
        return None
    status, _ = _read_registry(root)
    anchor = anchored_head_for(advisor_dir, root=root)   # None при absent/malformed/незарег.
    res["registry_malformed"] = (status == "malformed")
    res["anchor_head"] = anchor
    res["anchor_registered"] = anchor is not None
    res["anchor_match"] = None if anchor is None else (res["head"] == anchor)
    res["swap_suspect"] = res["anchor_match"] is False and res["ok"]  # внутри сходится, снаружи нет
    if res["anchor_match"] is False:
        res["ok"] = False
        res["tampered"] = True
    if status == "malformed":                            # битый реестр целостности → громкий провал
        res["ok"] = False
    return res


def freeze(advisor_dir, root=None):
    """Записать трекаемый corpus.lock.json = {gov_head} над ТЕКУЩИМ corpus.jsonl советника
    И зарегистрировать якорь в gov_heads.json (корень доски). Для шипованных корпусов (lenses/*)
    даёт git-переносимый эталон; для владельца — one-shot регистрация якоря старого советника."""
    from corpusbuild.paths import corpus_path, head_lock_path
    res = _verify_corpus(corpus_path(advisor_dir))
    if res is None:
        return None
    out = head_lock_path(advisor_dir)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"gov_head": res["head"], "n": res["n"]}, f, ensure_ascii=False, indent=2)
    anchored = register_head(advisor_dir, res["head"], n=res["n"], root=root)
    return {"path": out, "gov_head": res["head"], "n": res["n"],
            "anchored": bool(anchored), "anchor_key": (anchored or {}).get("key")}


def _verify_corpus(corpus_jsonl, expected_head=None):
    """Построить цепочку над corpus.jsonl, проверить целостность, дать голову-хеш + гистограмму
    тиров. Если передан expected_head (сохранённый в build.lock при сборке) — СВЕРИТЬ с ним:
    несовпадение = подмена corpus.jsonl ПОСЛЕ сборки (раньше цепь сверялась сама с собой —
    тавтология, ничего не ловила). head_match=None, если эталонной головы нет."""
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
    if len(sys.argv) < 3 or sys.argv[1] not in ("verify", "freeze"):
        print("Использование: python governance.py verify|freeze <dir | путь.jsonl>")
        sys.exit(1)
    from corpusbuild.paths import corpus_path  # резолвер, не литерал
    target = sys.argv[2]
    if sys.argv[1] == "freeze":                          # записать трекаемый эталон corpus.lock.json
        fr = freeze(target)
        if fr is None:
            print(f"[governance] нет corpus.jsonl: {target}"); sys.exit(1)
        anchor_note = f", якорь → gov_heads.json[{fr['anchor_key']}]" if fr["anchored"] else \
            ", якорь НЕ зарегистрирован (советник вне корня доски)"
        print(f"[governance] заморожен эталон: {fr['path']} ({fr['n']} записей, "
              f"голова {fr['gov_head'][:16]}…{anchor_note})")
        sys.exit(0)
    if target.endswith(".jsonl"):
        res = _verify_corpus(target)
        cj = target
    else:
        res = verify_advisor(target)
        cj = corpus_path(target)
    if res is None:
        print(f"[governance] нет corpus.jsonl: {cj}")
        sys.exit(1)
    if res.get("swap_suspect"):
        status = "❌ ЦЕПЬ ПОДМЕНЕНА ЦЕЛИКОМ? Внутри советник самосогласован, но голова ≠ якорю доски (gov_heads.json)"
    elif res["tampered"]:
        status = "❌ ПОДМЕНА: голова ≠ эталон"
    elif not res["ok"]:
        status = f"❌ ПОДМЕНА на записи #{res['broken']}"
    elif res.get("anchor_match"):
        status = "✅ целостна (сверена с якорем доски)"
    elif res["head_match"]:
        status = "✅ целостна (сверена с эталоном; якорь не зарегистрирован — `governance.py freeze` закрепит)"
    else:
        status = "✅ цепь консистентна (нет эталона — freeze/собрать для сверки)"
    tiers = " ".join(f"{k}:{v}" for k, v in sorted(res["tiers"].items()))
    print(f"[governance] {cj}")
    print(f"  записей {res['n']} · {status} · тиры [{tiers}]")
    print(f"  голова-хеш (отпечаток корпуса): {res['head'][:16]}…")
