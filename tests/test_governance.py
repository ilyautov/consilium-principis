"""Субстрат Барсика для Consilium: hash-chain провенанс + promote-gate.

Барсик = «Git для живой памяти». Примитив, который нужен контуру/Принцепсу: провенанс
не статичный конфиг, а tamper-evident леджер, где повышение тира (A→S→P = рост доверия)
проходит ГЕЙТ с доказательством, а цепочка хешей ловит подмену. fail-closed: нет
доказательства → повышение отклонено (остаёшься на текущем тире); понижение — всегда можно.
"""
import os, sys
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
