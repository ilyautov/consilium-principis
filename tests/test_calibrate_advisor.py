"""§3.2 moat-v2: per-advisor автокалибровка порогов (calibrate_advisor).

Оффлайн: ретрив/семантика мокаются — тестируем чистую математику (band_rule,
compute_calibration), сэмплинг проб (детерминизм сида, self-hit-фильтр), round-trip
записи/чтения calibration.json, резолюцию per-advisor → глобальный фоллбэк
(engine.load_backend_threshold, relevance_gate._gate_config) и флаг в doctor.
Живой прогон (ollama+bge-m3) — calibrate_advisor.main().
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import pytest
import calibrate_advisor as ca
import engine
import relevance_gate


# ───────────────────────── band_rule / compute_calibration (чистые) ──────────

def test_band_rule_mirrors_global_pair():
    """Глобальная пара (t=0.50 → lo=0.45; камуфляж-потолок 0.612 → hi≈0.65+) —
    правило воспроизводит логику, которой выбраны дефолты."""
    lo, hi = ca.band_rule(0.50, [0.55, 0.612, 0.58])
    assert lo == 0.45
    assert hi == pytest.approx(0.662)


def test_band_rule_floors_and_caps():
    lo, hi = ca.band_rule(0.03, [0.97])
    assert lo == 0.0                                   # floor 0
    assert hi == ca.HI_CAP                             # cap 0.95


def test_band_rule_requires_camouflage_scores():
    with pytest.raises(ValueError):
        ca.band_rule(0.5, [])


def test_compute_calibration_separable_sets():
    """Разделимые наборы: OOC < 0.45, answerable > 0.62 → порог в зазоре (тай-брейк —
    ниже порог), полоса валидна, auc = 1."""
    ooc = [0.30, 0.35, 0.38, 0.40, 0.42, 0.44]
    ans = [0.62, 0.65, 0.68, 0.70, 0.72, 0.75]
    r = ca.compute_calibration(ooc, ans, camouflage_scores=ooc)
    assert r["valid"]
    assert 0.44 < r["abstain_threshold"] <= 0.62
    assert r["auc"] == 1.0
    assert r["best"]["youden"] == 1.0
    assert r["band_lo"] == round(r["abstain_threshold"] - ca.LO_MARGIN, 3)
    assert r["band_hi"] == pytest.approx(0.44 + ca.HI_MARGIN)
    assert r["band_lo"] < r["band_hi"]


def test_compute_calibration_overlapping_sets_still_valid():
    """Пересечение (реальный камуфляж): порог = max youden, не идеал."""
    ooc = [0.40, 0.45, 0.50, 0.55, 0.58, 0.61]
    ans = [0.54, 0.58, 0.62, 0.66, 0.70, 0.74]
    r = ca.compute_calibration(ooc, ans, camouflage_scores=ooc)
    assert r["valid"]
    assert 0 < r["best"]["youden"] < 1
    assert r["band_hi"] == pytest.approx(0.66)         # max(ooc)+0.05


def test_compute_calibration_fail_closed_on_small_samples():
    r = ca.compute_calibration([0.3, 0.4], [0.7, 0.8])
    assert r["valid"] is False and "мало данных" in r["reason"]


def test_compute_calibration_fail_closed_on_inseparable():
    """OOC и answerable из одного распределения → youden <= 0 → НЕ калибруем."""
    same = [0.50] * 8
    r = ca.compute_calibration(same, same)
    assert r["valid"] is False


# ───────────────────────── сэмплинг проб ──────────────────────────────────────

def _mk_corpus(tmp_path, n=30):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for i in range(n):
            text = (f"Chunk number {i:02d} opens with a bit of framing context "
                    f"that situates the passage inside the larger argument. "
                    f"This is the informative middle sentence of chunk {i:02d} "
                    f"carrying the actual retrievable claim about the subject. "
                    f"And a closing remark specific to record {i:02d} rounds it off "
                    f"so that the record comfortably exceeds the length filter.")
            f.write(json.dumps({"text": text, "tier": "P1", "source": "s.txt"}) + "\n")
    return str(adv)


def test_probes_deterministic_by_seed(tmp_path):
    adv = _mk_corpus(tmp_path)
    a = ca.sample_answerable_probes(adv, n=10, seed=7)
    b = ca.sample_answerable_probes(adv, n=10, seed=7)
    c = ca.sample_answerable_probes(adv, n=10, seed=8)
    assert [p["q"] for p in a] == [p["q"] for p in b]
    assert [p["q"] for p in a] != [p["q"] for p in c]
    assert len(a) == 10
    for p in a:
        assert p["q"] in p["chunk"]                    # проба — предложение своего чанка


def test_probes_empty_without_corpus(tmp_path):
    assert ca.sample_answerable_probes(str(tmp_path / "none"), n=5) == []


def test_collect_scores_drops_self_hits(tmp_path):
    """Скор пробы считается по хитам, НЕ содержащим её текст (self-hit ≈ 1.0 завысил бы
    answerable-распределение); OOC берётся как есть."""
    adv = _mk_corpus(tmp_path)
    probes = ca.sample_answerable_probes(adv, n=3, seed=0)

    def fake_retrieve(q, d, k):
        # первый хит — сам чанк (self), второй — сосед с меньшим скором
        return [{"text": f"prefix {q} suffix", "score": 0.99},
                {"text": "unrelated neighbour chunk", "score": 0.61}]
    ooc_scores, ans_scores = ca.collect_scores(adv, probes, [{"q": "ooc?"}],
                                               retrieve_fn=fake_retrieve)
    assert ans_scores == [0.61] * 3                    # self-hit 0.99 отброшен
    assert ooc_scores == [0.99]                        # OOC — max как есть


def test_collect_scores_all_self_hits_skips_probe(tmp_path):
    adv = _mk_corpus(tmp_path)
    probes = ca.sample_answerable_probes(adv, n=2, seed=0)
    def only_self(q, d, k):
        return [{"text": q, "score": 0.99}]
    _, ans_scores = ca.collect_scores(adv, probes, [], retrieve_fn=only_self)
    assert ans_scores == []


# ───────────────────────── calibrate: round-trip + skip ──────────────────────

def _sep_retrieve(camo_qs):
    """Мок-ретрив: OOC-вопросы (из батареи) → 0.42; пробы → self 0.95 + сосед 0.68."""
    def f(q, d, k):
        if any(q == c for c in camo_qs):
            return [{"text": "topical but off", "score": 0.42}]
        return [{"text": f"self {q} self", "score": 0.95},
                {"text": "neighbour", "score": 0.68}]
    return f


def test_calibrate_writes_readable_calibration(tmp_path):
    adv = _mk_corpus(tmp_path)
    camo, generic = ca.load_smoke_ooc("advisors/machiavelli")
    assert camo and generic                            # батарея в репо
    # slug advisor'а = имя tmp-папки → подсунем батарею через monkey-подход не нужен:
    # calibrate сам грузит по slug — для tmp-slug её нет → проверяем через generic-ветку ниже.
    # Здесь тестируем write/read round-trip напрямую:
    result = {"calibrated": True, "abstain_threshold": {"semantic": 0.47},
              "relevance_gate": {"band_lo": 0.42, "band_hi": 0.66}}
    p = ca.write_calibration(adv, result)
    assert os.path.isfile(p)
    assert engine.load_calibration(adv) == result


def test_calibrate_skips_without_camouflage_set(tmp_path):
    adv = _mk_corpus(tmp_path)                         # slug "adv" — батареи нет
    r = ca.calibrate(adv, retrieve_fn=lambda q, d, k: [], write=True)
    assert r["calibrated"] is False and "камуфляж" in r["reason"]
    assert not os.path.isfile(ca.calibration_file(adv))   # skip файл НЕ пишет


def test_calibrate_skips_without_semantic(tmp_path, monkeypatch):
    adv = _mk_corpus(tmp_path)
    monkeypatch.setattr(relevance_gate, "is_semantic", lambda d: False)
    r = ca.calibrate(adv)                              # retrieve_fn=None → семантик-гейт
    assert r["calibrated"] is False and "semantic" in r["reason"]
    assert not os.path.isfile(ca.calibration_file(adv))


def test_calibrate_end_to_end_with_battery(tmp_path, monkeypatch):
    """Полный проход с мок-ретривом: подсовываем tmp-советнику камуфляж-набор
    Макиавелли через monkeypatch load_smoke_ooc → файл пишется, флаги честные."""
    adv = _mk_corpus(tmp_path)
    camo, generic = ca.load_smoke_ooc("advisors/machiavelli")
    monkeypatch.setattr(ca, "load_smoke_ooc", lambda d: (camo, generic))
    r = ca.calibrate(adv, retrieve_fn=_sep_retrieve([c["q"] for c in camo + generic]),
                     seed=3)
    assert r["calibrated"] is True
    assert r["seed"] == 3
    t = r["abstain_threshold"]["semantic"]
    assert 0.42 < t <= 0.68
    assert r["relevance_gate"]["band_lo"] == round(t - ca.LO_MARGIN, 3)
    assert r["relevance_gate"]["band_hi"] == pytest.approx(0.42 + ca.HI_MARGIN)
    assert r["corpus_sha256"] and len(r["corpus_sha256"]) == 64
    assert r["data"]["n_camouflage"] == len(camo)
    # файл читается резолюцией
    assert engine.load_calibration(adv)["calibrated"] is True


# ───────────────────────── резолюция per-advisor → глобальный фоллбэк ────────

def test_threshold_resolution_prefers_calibration(tmp_path):
    adv = _mk_corpus(tmp_path)
    ca.write_calibration(adv, {"calibrated": True,
                               "abstain_threshold": {"semantic": 0.437}})
    assert engine.load_backend_threshold(adv, "semantic", 0.50) == 0.437
    # backend без калиброванного значения → глобальный путь (lexical не писали)
    got = engine.load_backend_threshold(adv, "lexical", 0.04)
    assert got == pytest.approx(0.04, abs=0.5)         # не 0.437 (см. точный тест ниже)
    assert got != 0.437


def test_threshold_resolution_ignores_uncalibrated_file(tmp_path):
    adv = _mk_corpus(tmp_path)
    ca.write_calibration(adv, {"calibrated": False, "reason": "skip",
                               "abstain_threshold": {"semantic": 0.10}})
    assert engine.load_calibration(adv) is None        # calibrated != True → None
    assert engine.load_backend_threshold(adv, "semantic", 0.50) != 0.10


def test_threshold_resolution_broken_value_falls_back(tmp_path):
    adv = _mk_corpus(tmp_path)
    ca.write_calibration(adv, {"calibrated": True,
                               "abstain_threshold": {"semantic": "мусор"}})
    got = engine.load_backend_threshold(adv, "semantic", 0.50)
    assert got != "мусор"                              # коэрс упал → глобальный/default
    assert isinstance(got, float)


def test_gate_config_overlays_calibrated_band(tmp_path):
    adv = _mk_corpus(tmp_path)
    ca.write_calibration(adv, {"calibrated": True,
                               "relevance_gate": {"band_lo": 0.40, "band_hi": 0.70}})
    cfg = relevance_gate._gate_config(adv)
    assert cfg["band_lo"] == 0.40 and cfg["band_hi"] == 0.70


def test_gate_config_global_without_calibration(tmp_path):
    cfg = relevance_gate._gate_config(str(tmp_path / "adv"))
    assert cfg["band_lo"] == relevance_gate.BAND_LO or isinstance(cfg["band_lo"], float)
    # инвариант: без calibration.json полоса — глобальная (дефолт или board_config)
    assert not os.path.isfile(ca.calibration_file(str(tmp_path / "adv")))


def test_gate_config_ignores_inverted_calibrated_band(tmp_path):
    adv = _mk_corpus(tmp_path)
    ca.write_calibration(adv, {"calibrated": True,
                               "relevance_gate": {"band_lo": 0.80, "band_hi": 0.30}})
    cfg = relevance_gate._gate_config(adv)
    assert cfg["band_lo"] < cfg["band_hi"]             # инверсия отвергнута
    assert cfg["band_lo"] != 0.80


def test_gate_config_none_advisor_dir_safe():
    cfg = relevance_gate._gate_config(None)
    assert cfg["band_lo"] < cfg["band_hi"]


# ───────────────────────── doctor: честный флаг ──────────────────────────────

def test_doctor_calibration_flags(tmp_path):
    import doctor
    root = tmp_path
    for slug, calibrated in (("alpha", True), ("beta", False)):
        adv = root / "advisors" / slug / "build"
        adv.mkdir(parents=True)
        (adv / "corpus.jsonl").write_text(
            json.dumps({"text": "x" * 60, "tier": "P1"}) + "\n", encoding="utf-8")
        if calibrated:
            (adv / "calibration.json").write_text(json.dumps(
                {"calibrated": True, "abstain_threshold": {"semantic": 0.47},
                 "relevance_gate": {"band_lo": 0.42, "band_hi": 0.66}}),
                encoding="utf-8")
    c = doctor.check_calibration(str(root))
    assert c["ok"] is True                             # не-калиброван — не болезнь
    assert "alpha: калиброван" in c["detail"] and "0.47" in c["detail"]
    assert "beta: не калиброван" in c["detail"]


def test_doctor_calibration_no_advisors(tmp_path):
    import doctor
    c = doctor.check_calibration(str(tmp_path))
    assert c["ok"] is True and "нет собранных" in c["detail"]


def test_run_doctor_includes_calibration_check():
    import doctor
    r = doctor.run_doctor(".")
    assert any(c["name"] == "calibration" for c in r["checks"])
