"""Стартовый совет в один шаг: PD-мудрецы → fetch → манифест → ВАЛИДАЦИЯ → build.

Чинит главную фрикцию cold-start: «пустая доска — норма», но новый юзер упирается в холодный
стол. seed_council собирает курированный набор public-domain мудрецов за один вызов. Реестр несёт
ВЫВЕРЕННЫЕ под издание манифесты (тиры с region-маркерами) — ценность в том, что суждение о тирах
сделано один раз. Манифест-гейт встроен: маркер не в скачанном тексте → советник не идёт в сборку
(не молчаливый съезд рва). fetch/build инъектируются → тест офлайн.
"""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from seed import seed_one, seed_council, SEED_ADVISORS


def _fake_fetch_writing(text):
    def fetch(adv_dir, url, source_file):
        sd = os.path.join(adv_dir, "sources")
        os.makedirs(sd, exist_ok=True)
        p = os.path.join(sd, source_file)
        open(p, "w", encoding="utf-8").write(text)
        return p
    return fetch


def _fake_build(adv_dir):
    return {"ok": True, "status": {"name": os.path.basename(adv_dir), "blue_eligible": True}}


def test_seed_one_happy_path():
    spec = {"name": "sage", "display": "Мудрец", "url": "http://x", "source_file": "s.txt",
            "manifest_entry": {"tier": "P1", "regions": [{"tier": "B", "until": "BOOK ONE"},
                                                         {"tier": "P1", "from": "BOOK ONE"}]}}
    with tempfile.TemporaryDirectory() as t:
        fetch = _fake_fetch_writing("preface stuff\nBOOK ONE\nthe real text here")
        res = seed_one(spec, t, fetch, _fake_build)
        assert res["ok"] is True
        mp = os.path.join(t, "advisors", "sage", "sources", "manifest.json")
        assert os.path.isfile(mp)
        assert json.load(open(mp))["s.txt"]["tier"] == "P1"


def test_seed_one_gate_blocks_bad_marker():
    spec = {"name": "sage", "display": "Мудрец", "url": "http://x", "source_file": "s.txt",
            "manifest_entry": {"tier": "P1", "regions": [{"tier": "P1", "from": "MARKER NOT PRESENT"}]}}
    with tempfile.TemporaryDirectory() as t:
        fetch = _fake_fetch_writing("текст без маркера")
        res = seed_one(spec, t, fetch, _fake_build)
        assert res["ok"] is False and res["stage"] == "manifest"


def test_seed_one_handles_fetch_failure():
    spec = {"name": "sage", "display": "X", "url": "http://x", "source_file": "s.txt",
            "manifest_entry": {"tier": "P1"}}
    with tempfile.TemporaryDirectory() as t:
        res = seed_one(spec, t, lambda *a: None, _fake_build)  # fetch вернул None
        assert res["ok"] is False and res["stage"] == "fetch"


def test_real_fetch_soft_fails_when_collect_errors(monkeypatch):
    # #7: collect_pd падает (оффлайн / файрвол / блок Gutenberg) → _real_fetch отдаёт None,
    # а НЕ сырой CalledProcessError-traceback на первом шаге онбординга (seed_one сделает мягко).
    import seed
    def boom(*a, **k):
        raise seed.subprocess.CalledProcessError(1, "collect_pd")
    monkeypatch.setattr(seed.subprocess, "run", boom)
    with tempfile.TemporaryDirectory() as t:
        assert seed._real_fetch(t, "http://x", "s.txt") is None


def test_seed_council_continues_past_failures():
    specs = [
        {"name": "good", "display": "G", "url": "http://x", "source_file": "s.txt",
         "manifest_entry": {"tier": "P1"}},
        {"name": "bad", "display": "B", "url": "http://x", "source_file": "s.txt",
         "manifest_entry": {"tier": "P1", "regions": [{"tier": "P1", "from": "NOPE"}]}},
    ]
    with tempfile.TemporaryDirectory() as t:
        fetch = _fake_fetch_writing("just body no markers")
        results = seed_council(specs, t, fetch, _fake_build)
        assert len(results) == 2
        assert results[0]["ok"] is True and results[1]["ok"] is False


def test_registry_entries_well_formed():
    assert len(SEED_ADVISORS) >= 1
    for s in SEED_ADVISORS:
        assert {"name", "display", "url", "source_file", "manifest_entry"} <= set(s)
        assert s["manifest_entry"]["tier"] in ("P1", "P2", "S1", "S2", "B", "A")
