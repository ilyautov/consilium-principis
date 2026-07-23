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


def _happy_spec(name="sage", display="Мудрец"):
    return {"name": name, "display": display, "url": "http://x", "source_file": "s.txt",
            "manifest_entry": {"tier": "P1", "regions": [{"tier": "B", "until": "BOOK ONE"},
                                                         {"tier": "P1", "from": "BOOK ONE"}]}}


_HAPPY_TEXT = "preface stuff\nBOOK ONE\nthe real text here"


def test_seed_one_writes_starter_persona():
    # F1: без persona.md seeded-советник невидим для diversity_check/board_init. seed пишет минимум.
    with tempfile.TemporaryDirectory() as t:
        seed_one(_happy_spec(), t, _fake_fetch_writing(_HAPPY_TEXT), _fake_build)
        pm = os.path.join(t, "advisors", "sage", "persona.md")
        assert os.path.isfile(pm)
        assert "Мудрец" in open(pm, encoding="utf-8").read()   # display-имя проставлено


def test_seed_one_does_not_clobber_existing_persona():
    # Ручные правки священны: повторный seed НЕ затирает уже написанный persona.md.
    with tempfile.TemporaryDirectory() as t:
        adv = os.path.join(t, "advisors", "sage")
        os.makedirs(adv)
        pm = os.path.join(adv, "persona.md")
        open(pm, "w", encoding="utf-8").write("---\nname: РУЧНАЯ ПРАВКА\nlenses: [x]\ndomains: [y]\n---\n")
        seed_one(_happy_spec(), t, _fake_fetch_writing(_HAPPY_TEXT), _fake_build)
        assert "РУЧНАЯ ПРАВКА" in open(pm, encoding="utf-8").read()


def test_seeded_board_recognized_by_diversity_check():
    # F1 сквозной: после seed 2 фигур diversity_check НЕ падает в error, а даёт insufficient_data
    # (доска опознана, метаданные надо заполнить) — вместо «Не нашёл persona.md минимум у двоих».
    sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
    from diversity_check import check
    specs = [_happy_spec("sage-a", "Мудрец А"), _happy_spec("sage-b", "Мудрец Б")]
    with tempfile.TemporaryDirectory() as t:
        seed_council(specs, t, _fake_fetch_writing(_HAPPY_TEXT), _fake_build)
        out = check([os.path.join(t, "advisors", "sage-a"), os.path.join(t, "advisors", "sage-b")])
    assert "error" not in out
    assert out["verdict"] == "insufficient_data"


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
