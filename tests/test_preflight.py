"""Преднастройка заседания — связка Принцепс + советники + линзы в одну стартовую картину."""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from preflight import preflight
from corpusbuild.paths import corpus_path


def _mk_advisor(root, name, chunks):
    """chunks = list of (tier, text). Кладёт в правильный путь corpus_path."""
    adv = os.path.join(root, "advisors", name)
    cp = corpus_path(adv)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    with open(cp, "w", encoding="utf-8") as f:
        for tier, text in chunks:
            f.write(json.dumps({"source": "s.txt", "tier": tier, "text": text}, ensure_ascii=False) + "\n")
    return adv


def _mk_lens(root, fn, name):
    d = os.path.join(root, "lenses")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {name}\ngrade: frame-lens\nmarker_ceiling: 🟡\naxis: тест\n---\n## Кернелы\n- **K:** v\n")


def _mk_principis(root, mode="rigor"):
    with open(os.path.join(root, "principis.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: T\ninterface_mode: {mode}\nowner: principis\n---\n## Кто ты\nx\n")


def test_ready_when_grounded_advisor_and_lens():
    with tempfile.TemporaryDirectory() as t:
        _mk_advisor(t, "mach", [("P1", "feared more than loved"), ("S1", "комментарий")])
        _mk_lens(t, "cfo.md", "CFO")
        _mk_principis(t, "rigor")
        pf = preflight(t)
        assert pf["ready"] is True
        assert pf["principis"]["ok"] is True
        assert pf["principis"]["interface_mode"] == "rigor"
        a = next(a for a in pf["advisors"] if a["name"] == "mach")
        assert a["blue_eligible"] is True            # есть P1
        assert a["tiers"]["S1"] == 1
        assert any(l["name"] == "CFO" for l in pf["lenses"])


def test_advisor_without_p1_is_not_blue_eligible():
    with tempfile.TemporaryDirectory() as t:
        _mk_advisor(t, "comm", [("S1", "только комментарий"), ("B", "front-matter")])
        _mk_lens(t, "x.md", "X")
        pf = preflight(t)
        a = next(a for a in pf["advisors"] if a["name"] == "comm")
        assert a["has_corpus"] is True
        assert a["blue_eligible"] is False           # ни P1, ни P2 → не может давать 🔵


def test_empty_root_not_ready_and_principis_defaults():
    with tempfile.TemporaryDirectory() as t:
        pf = preflight(t)
        assert pf["ready"] is False
        assert pf["advisors"] == []
        assert pf["principis"]["ok"] is False
        assert pf["principis"]["interface_mode"] == "rigor"   # fail-safe дефолт


def test_lens_without_advisor_not_ready():
    with tempfile.TemporaryDirectory() as t:
        _mk_lens(t, "cfo.md", "CFO")                  # линза есть, грунтованного советника нет
        assert preflight(t)["ready"] is False
