"""Субстрат Барсика для Consilium: hash-chain провенанс + promote-gate.

Барсик = «Git для живой памяти». Примитив, который нужен контуру/Принцепсу: провенанс
не статичный конфиг, а tamper-evident леджер, где повышение тира (A→S→P = рост доверия)
проходит ГЕЙТ с доказательством, а цепочка хешей ловит подмену. fail-closed: нет
доказательства → повышение отклонено (остаёшься на текущем тире); понижение — всегда можно.
"""
import os, sys
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from governance import (
    record_hash, build_chain, verify_chain, promote_gate, TIER_ORDER,
)


def test_hash_is_deterministic_and_chains_prev():
    r = {"source": "telegram:ilya", "tier": "P1", "text": "привет"}
    h1 = record_hash(r, "GENESIS")
    h2 = record_hash(r, "GENESIS")
    assert h1 == h2                          # детерминизм
    h_other = record_hash(r, h1)
    assert h_other != h1                     # prev влияет → цепочка


def test_build_chain_links_each_to_previous():
    recs = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    chain = build_chain(recs)
    assert len(chain) == 3
    assert chain[0]["prev"] == "GENESIS"
    assert chain[1]["prev"] == chain[0]["hash"]   # каждый ссылается на предыдущий
    assert chain[2]["prev"] == chain[1]["hash"]
    assert len({c["hash"] for c in chain}) == 3   # все хеши различны


def test_verify_clean_chain_passes():
    chain = build_chain([{"text": "a"}, {"text": "b"}])
    ok, broken = verify_chain(chain)
    assert ok is True
    assert broken is None


def test_verify_detects_tampered_record():
    chain = build_chain([{"text": "a"}, {"text": "b"}, {"text": "c"}])
    chain[1]["record"]["text"] = "ПОДМЕНА"   # тронули содержимое после факта
    ok, broken = verify_chain(chain)
    assert ok is False
    assert broken == 1                       # первый сломанный индекс


def test_promote_needs_evidence_else_denied_fail_closed():
    # A → P1 = рост доверия. Без доказательства → отклонено, остаёмся на A.
    assert promote_gate("A", "P1", evidence=None) == "A"
    assert promote_gate("A", "P1", evidence="") == "A"
    # с доказательством — повышение разрешено
    assert promote_gate("A", "P1", evidence="manifest:sources/the-prince.txt#P1") == "P1"


def test_demotion_always_allowed_without_evidence():
    # P1 → A = падение доверия (fail-closed безопасно) — доказательство не требуется
    assert promote_gate("P1", "A", evidence=None) == "A"
    assert promote_gate("S1", "S2", evidence=None) == "S2"


def test_equal_tier_is_noop():
    assert promote_gate("S1", "S1", evidence=None) == "S1"


def test_tier_order_p1_most_authoritative():
    assert TIER_ORDER["P1"] < TIER_ORDER["S1"] < TIER_ORDER["A"]


def test_unknown_tier_treated_as_least_authoritative():
    # неизвестный тир → как A (fail-closed): повышение К нему не требует доказательства,
    # повышение ОТ него требует.
    assert promote_gate("ZZZ", "P1", evidence=None) == "ZZZ"   # нет доказательства → отказ
    assert promote_gate("P1", "ZZZ", evidence=None) == "ZZZ"   # к менее авторитетному — можно


def test_lock_head_catches_corpus_tampering(tmp_path):
    # P1-фикс: gov_head пишется в build.lock при сборке; verify сверяет с ним. Подмена
    # corpus.jsonl ПОСЛЕ сборки → голова разъезжается → tampered (раньше цепь сверялась сама
    # с собой и всегда была ok — тавтология).
    import json
    from corpusbuild import pipeline, paths
    from governance import _verify_corpus, _lock_head
    adv = str(tmp_path / "adv")
    os.makedirs(os.path.join(adv, "sources"))
    with open(os.path.join(adv, "sources", "x.txt"), "w", encoding="utf-8") as f:
        f.write("First principle of strategy.\nSecond line of the canon.\n")
    pipeline.build(adv)
    cj, head = paths.corpus_path(adv), _lock_head(paths.lock_path(adv))
    assert head                                              # эталонная голова записана
    clean = _verify_corpus(cj, expected_head=head)
    assert clean["head_match"] is True and clean["tampered"] is False and clean["ok"]
    with open(cj, "a", encoding="utf-8") as f:               # подмена постфактум
        f.write(json.dumps({"text": "INJECTED", "tier": "P1", "source": "x"}, ensure_ascii=False) + "\n")
    bad = _verify_corpus(cj, expected_head=head)
    assert bad["tampered"] is True and bad["ok"] is False    # голова ≠ эталон → поймано


# ─────────────── якорь ВНЕ подменяемой папки (gov_heads.json, защита от «шипованного» корпуса) ───────────────

def _built_advisor(root, name, body):
    """Собрать советника под root через легитимный pipeline (write_lock регистрирует якорь)."""
    from corpusbuild import pipeline
    adv = os.path.join(root, "advisors", name)
    os.makedirs(os.path.join(adv, "sources"))
    with open(os.path.join(adv, "sources", "x.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    pipeline.build(adv)
    return adv


def test_anchor_detects_self_consistent_whole_dir_swap(tmp_path, monkeypatch):
    # Противник подменяет ВСЮ папку советника самосогласованным двойником: corpus.jsonl +
    # build.lock.json + corpus.lock.json сходятся между собой → внутренние проверки проходят.
    # Якорь в gov_heads.json (корень доски, ВНЕ папки) обязан поймать подмену целиком.
    import shutil
    from corpusbuild import paths as cp
    from governance import verify_advisor, freeze
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)     # корень доски = tmp (легит. сборка регистрирует)
    adv = _built_advisor(root, "sage", "Первый принцип стратегии.\nВторая строка канона.\n")
    ok = verify_advisor(adv, root=root)
    assert ok["ok"] and ok["anchor_match"] is True and ok["swap_suspect"] is False

    fake = _built_advisor(root, "fake-twin", "ШИПОВАННЫЙ текст противника.\nЕщё строка яда.\n")
    freeze(fake, root=root)                                   # у двойника есть и corpus.lock.json
    # подмена ЦЕЛИКОМ: перенести самосогласованные артефакты двойника в папку жертвы
    shutil.copy(cp.corpus_path(fake), cp.corpus_path(adv))
    shutil.copy(cp.lock_path(fake), cp.lock_path(adv))
    shutil.copy(cp.head_lock_path(fake), cp.head_lock_path(adv))
    bad = verify_advisor(adv, root=root)
    assert bad["broken"] is None                              # цепь двойника САМОсогласована...
    assert bad["head_match"] is True                          # ...и внутренние lock'и сходятся...
    assert bad["swap_suspect"] is True                        # ...но якорь снаружи ловит подмену
    assert bad["tampered"] is True and bad["ok"] is False


def test_legit_rebuild_updates_anchor(tmp_path, monkeypatch):
    from corpusbuild import pipeline, paths as cp
    from governance import verify_advisor, load_registry
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)
    adv = _built_advisor(root, "sage", "Старый корпус советника.\n")
    old = load_registry(root)["advisors/sage"]["gov_head"]
    with open(os.path.join(adv, "sources", "x.txt"), "w", encoding="utf-8") as f:
        f.write("Новый легитимный корпус после пересборки.\n")
    pipeline.build(adv)                                       # легитимная пересборка
    new = load_registry(root)["advisors/sage"]["gov_head"]
    assert new != old                                         # якорь обновился вместе со сборкой
    res = verify_advisor(adv, root=root)
    assert res["ok"] and res["anchor_match"] is True          # и сверка снова зелёная


def test_unregistered_anchor_is_warning_not_fail(tmp_path):
    # Миграция: советник без записи в реестре (или вовсе без gov_heads.json) — НЕ провал.
    from governance import verify_advisor
    adv = _built_advisor(str(tmp_path), "legacy", "Корпус до эпохи якорей.\n")
    # реестра в tmp_path нет (write_lock с реальным project_root пропустил внешний каталог)
    res = verify_advisor(adv, root=str(tmp_path))
    assert res["ok"] is True and res["tampered"] is False
    assert res["anchor_registered"] is False and res["anchor_match"] is None
    assert res["swap_suspect"] is False


def test_register_head_skips_advisor_outside_root(tmp_path):
    # Советник ВНЕ корня доски: якорить нечем — no-op, реестр не создаётся (нет мусорных ключей).
    from governance import register_head, registry_path
    outside = tmp_path / "elsewhere" / "adv"
    os.makedirs(outside)
    root = str(tmp_path / "board")
    os.makedirs(root)
    assert register_head(str(outside), "deadbeef", root=root) is None
    assert not os.path.exists(registry_path(root))


def test_freeze_registers_anchor_one_shot(tmp_path):
    # Владельческий one-shot: freeze пишет corpus.lock.json И регистрирует якорь в gov_heads.json.
    from governance import freeze, anchored_head_for, verify_advisor
    root = str(tmp_path)
    adv = _built_advisor(root, "legacy", "Старый советник получает якорь одним шагом.\n")
    fr = freeze(adv, root=root)
    assert fr["anchored"] is True and fr["anchor_key"] == "advisors/legacy"
    assert anchored_head_for(adv, root=root) == fr["gov_head"]
    res = verify_advisor(adv, root=root)
    assert res["ok"] and res["anchor_match"] is True


def test_malformed_registry_is_loud_failure_not_migration_warning(tmp_path):
    # Битый gov_heads.json ≠ отсутствующий: truncated/не-JSON — это ПОРЧА (оборванная запись/
    # подмена), обязана быть ГРОМКИМ провалом (ok=False, registry_malformed), а не молчаливым
    # отключением детекта под видом «ещё не мигрировали».
    from governance import verify_advisor, registry_path
    root = str(tmp_path)
    adv = _built_advisor(root, "sage", "Корпус при сломанном реестре.\n")
    with open(registry_path(root), "w", encoding="utf-8") as f:
        f.write('{"advisors/sage": {"gov_head": "abc"')     # усечённый JSON (оборванная запись)
    res = verify_advisor(adv, root=root)
    assert res["registry_malformed"] is True
    assert res["ok"] is False                                # fail-closed, не мягкое предупреждение
    assert res["anchor_registered"] is False


def test_non_dict_registry_is_malformed(tmp_path):
    from governance import verify_advisor, registry_path
    root = str(tmp_path)
    adv = _built_advisor(root, "sage", "Корпус.\n")
    with open(registry_path(root), "w", encoding="utf-8") as f:
        f.write('["not", "a", "dict"]')
    res = verify_advisor(adv, root=root)
    assert res["registry_malformed"] is True and res["ok"] is False


def test_absent_registry_is_migration_warning_not_malformed(tmp_path):
    # Отсутствие реестра (внешний каталог, реестр не создавался) — мягкая миграция, НЕ порча.
    from governance import verify_advisor
    adv = _built_advisor(str(tmp_path), "legacy", "Корпус без реестра.\n")
    res = verify_advisor(adv, root=str(tmp_path))
    assert res["registry_malformed"] is False
    assert res["anchor_registered"] is False and res["ok"] is True


def test_register_head_atomic_no_partial_file_on_failure(tmp_path, monkeypatch):
    # Симулируем падение json.dump В ПРОЦЕССЕ записи: gov_heads.json НЕ должен остаться усечённым,
    # временный .tmp не должен утечь. os.replace атомарен → читатель видит всё-или-ничего.
    import json as _json
    import governance
    from governance import register_head, registry_path, _read_registry
    root = str(tmp_path)
    register_head(os.path.join(root, "advisors", "a"), "HEAD_ONE", n=1, root=root)  # валидный старт
    assert _read_registry(root)[0] == "ok"

    orig_dump = _json.dump
    def boom(obj, fp, **kw):
        fp.write('{"partial": ')                             # частично записали...
        raise IOError("disk full")                           # ...и упали
    monkeypatch.setattr(governance.json, "dump", boom)
    with pytest.raises(IOError):
        register_head(os.path.join(root, "advisors", "b"), "HEAD_TWO", n=1, root=root)
    monkeypatch.setattr(governance.json, "dump", orig_dump)
    # старый валидный контент цел (os.replace не выполнился), .tmp-огрызки убраны
    status, reg = _read_registry(root)
    assert status == "ok" and reg["advisors/a"]["gov_head"] == "HEAD_ONE"
    leftovers = [f for f in os.listdir(root) if f.startswith(".gov_heads.")]
    assert leftovers == []


# ─────────────── РАЗДЕЛЕНИЕ РЕЕСТРА ПО ШИПУЕМОСТИ (приватность/копирайт-файрвол) ───────────────
# gov_heads.json ТРЕКАЕТСЯ и едет в public-репо/инсталл → в нём ТОЛЬКО шипуемое (lenses/* PD/CC).
# Приватные советники (advisors/* = реальные живые люди) якорятся в gov_heads.local.json —
# GITIGNORED, per-user. Один git add -A не должен утащить имена реальных людей в git.

def test_register_private_advisor_lands_in_local_not_tracked(tmp_path):
    from governance import (register_head, registry_path, local_registry_path,
                            _read_registry_file)
    root = str(tmp_path)
    register_head(os.path.join(root, "advisors", "real-person"), "PRIVHEAD", n=7, root=root)
    # приватный якорь — в ЛОКАЛЬНОМ (gitignored) файле
    ls, local = _read_registry_file(local_registry_path(root))
    assert ls == "ok" and local["advisors/real-person"]["gov_head"] == "PRIVHEAD"
    # трекаемый файл НЕ создан / НЕ содержит приватных ключей
    ts, tracked = _read_registry_file(registry_path(root))
    assert "advisors/real-person" not in tracked
    assert not os.path.exists(registry_path(root)) or all(
        not k.startswith("advisors/") for k in tracked)


def test_register_shippable_lens_lands_in_tracked_not_local(tmp_path):
    from governance import (register_head, registry_path, local_registry_path,
                            _read_registry_file)
    root = str(tmp_path)
    register_head(os.path.join(root, "lenses", "strategist"), "LENSHEAD", n=31, root=root)
    ts, tracked = _read_registry_file(registry_path(root))
    assert ts == "ok" and tracked["lenses/strategist"]["gov_head"] == "LENSHEAD"
    # локальный файл не задет шипуемой линзой
    assert not os.path.exists(local_registry_path(root))


def test_verify_advisor_reads_union_private_anchor_from_local(tmp_path, monkeypatch):
    # Приватный советник, собранный легит-сборкой → якорь в local; verify обязан читать ОБЪЕДИНЕНИЕ
    # (local ∪ tracked) и находить его. Трекаемый файл при этом чист от приватного имени.
    from corpusbuild import paths as cp
    from governance import (verify_advisor, registry_path, local_registry_path,
                            _read_registry_file, anchored_head_for)
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)
    adv = _built_advisor(root, "real-person", "Приватный корпус живого человека.\n")
    # якорь ушёл в local, tracked чист от advisors/*
    ls, local = _read_registry_file(local_registry_path(root))
    assert "advisors/real-person" in local
    ts, tracked = _read_registry_file(registry_path(root))
    assert all(not k.startswith("advisors/") for k in tracked)
    # union-резолюция: verify находит якорь и сходится
    assert anchored_head_for(adv, root=root) == local["advisors/real-person"]["gov_head"]
    res = verify_advisor(adv, root=root)
    assert res["ok"] and res["anchor_match"] is True and res["anchor_registered"] is True


def test_migration_evacuates_legacy_advisors_from_tracked(tmp_path, monkeypatch):
    # Легаси/грязное состояние: трекаемый gov_heads.json уже содержит advisors/* (ровно текущая
    # ситуация рабочего дерева). Само-лечение при load/verify: приватные ключи переезжают в local,
    # трекаемый переписывается БЕЗ них — один раз, прозрачно.
    import json as _json
    from corpusbuild import paths as cp
    from governance import (verify_advisor, registry_path, local_registry_path,
                            _read_registry_file)
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)
    adv = _built_advisor(root, "real-person", "Приватный корпус.\n")
    real_head = _read_registry_file(local_registry_path(root))[1]["advisors/real-person"]["gov_head"]
    # засеять ГРЯЗНЫЙ трекаемый файл: приватный ключ + шипуемая линза (как в рабочем дереве)
    dirty = {"advisors/real-person": {"gov_head": real_head, "n": 1},
             "lenses/strategist": {"gov_head": "L" * 64, "n": 31}}
    with open(registry_path(root), "w", encoding="utf-8") as f:
        _json.dump(dirty, f)
    # триггерим лечение (verify_advisor читает объединение и лечит)
    verify_advisor(adv, root=root)
    ts, tracked = _read_registry_file(registry_path(root))
    ls, local = _read_registry_file(local_registry_path(root))
    assert ts == "ok" and "advisors/real-person" not in tracked      # приватное эвакуировано
    assert tracked["lenses/strategist"]["gov_head"] == "L" * 64      # шипуемое осталось
    assert local["advisors/real-person"]["gov_head"] == real_head    # приватное живёт локально


def test_tracked_never_gains_advisors_after_heal(tmp_path, monkeypatch):
    # Инвариант файрвола: после лечения ни одна операция чтения/верификации не возвращает
    # advisors/* в трекаемый файл.
    from corpusbuild import paths as cp
    from governance import (verify_advisor, load_registry, registry_path, _read_registry_file)
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)
    adv = _built_advisor(root, "real-person", "Приватный корпус.\n")
    load_registry(root)                                              # union-чтение
    verify_advisor(adv, root=root)                                   # верификация
    ts, tracked = _read_registry_file(registry_path(root))
    assert all(not k.startswith("advisors/") for k in tracked)


def test_local_registry_malformed_is_loud_failure(tmp_path, monkeypatch):
    # fail-closed сохранён для ОБОИХ файлов: битый local (усечённая/оборванная приватная запись) —
    # это ПОРЧА, не «ещё не мигрировали»; verify обязан кричать.
    from corpusbuild import paths as cp
    from governance import verify_advisor, local_registry_path
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)
    adv = _built_advisor(root, "real-person", "Приватный корпус.\n")
    with open(local_registry_path(root), "w", encoding="utf-8") as f:
        f.write('{"advisors/real-person": {"gov_head": "abc"')      # усечённый JSON
    res = verify_advisor(adv, root=root)
    assert res["registry_malformed"] is True and res["ok"] is False


def test_register_local_atomic_no_partial_on_failure(tmp_path, monkeypatch):
    # Атомарная запись сохранена для local: падение json.dump не оставляет усечённый local-реестр.
    import json as _json
    import governance
    from governance import register_head, local_registry_path, _read_registry_file
    root = str(tmp_path)
    register_head(os.path.join(root, "advisors", "a"), "HEAD_ONE", n=1, root=root)
    assert _read_registry_file(local_registry_path(root))[0] == "ok"
    def boom(obj, fp, **kw):
        fp.write('{"partial": ')
        raise IOError("disk full")
    monkeypatch.setattr(governance.json, "dump", boom)
    with pytest.raises(IOError):
        register_head(os.path.join(root, "advisors", "b"), "HEAD_TWO", n=1, root=root)
    monkeypatch.setattr(governance.json, "dump", _json.dump)
    status, reg = _read_registry_file(local_registry_path(root))
    assert status == "ok" and reg["advisors/a"]["gov_head"] == "HEAD_ONE"
    assert [f for f in os.listdir(root) if f.startswith(".gov_heads.")] == []


def test_install_does_not_ship_local_registry():
    # Копирайт-файрвол на инсталле: RUNTIME шипует трекаемый gov_heads.json, но НИКОГДА
    # gov_heads.local.json (приватные имена per-user).
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "install_mod", os.path.join(HERE, "..", "install.py"))
    install = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install)
    assert "gov_heads.json" in install.RUNTIME
    assert "gov_heads.local.json" not in install.RUNTIME


def test_doctor_gov_anchor_ok_for_private_advisor_via_local(tmp_path, monkeypatch):
    from corpusbuild import paths as cp
    from doctor import check_gov_anchors
    root = str(tmp_path)
    monkeypatch.setattr(cp, "project_root", lambda: root)
    _built_advisor(root, "real-person", "Приватный корпус, якорь в local.\n")
    c = check_gov_anchors(root)
    assert c["ok"] is True and "якорь совпал: 1" in c["detail"]
