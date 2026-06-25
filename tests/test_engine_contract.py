import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from engine import Engine, Passage, AbstainResult, FidelityResult


class FakeEngine(Engine):
    name = "fake"
    def retrieve(self, question, advisor_dir, top_k=3):
        return [Passage(text="alpha beta", score=0.8, source="x"),
                Passage(text="gamma", score=0.3, source="y")][:top_k]
    def build_index(self, advisor_dir):
        return {}
    def abstain_threshold(self, advisor_dir):
        return 0.5


def test_passage_shape():
    p = Passage(text="t", score=0.1, source="s")
    assert (p.text, p.score, p.source) == ("t", 0.1, "s")

def test_abstain_check_uses_top_score():
    e = FakeEngine()
    r = e.abstain_check("q", "/tmp/adv")
    assert isinstance(r, AbstainResult)
    assert r.abstain is False and r.max_score == 0.8 and r.threshold == 0.5

def test_abstain_when_below_threshold(monkeypatch):
    e = FakeEngine()
    monkeypatch.setattr(e, "retrieve", lambda *a, **k: [Passage("t", 0.2, "s")])
    r = e.abstain_check("q", "/tmp/adv")
    assert r.abstain is True and r.max_score == 0.2


def test_fidelity_check_hit_and_miss():
    import tempfile, os, json
    from engine import Passage
    class E(FakeEngine):
        pass
    with tempfile.TemporaryDirectory() as t:
        adv = os.path.join(t, "adv"); os.makedirs(adv)
        with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"source": "src", "text": "bear with them or teach them"}) + "\n")
        e = E()
        hit = e.fidelity_check("bear with them", adv)
        assert hit.status == "🔵" and hit.verbatim is True and hit.source == "src"
        miss = e.fidelity_check("you have power over your mind", adv)
        assert miss.status == "🟡" and miss.verbatim is False and miss.source == ""

def test_abstain_check_empty_retrieve_abstains(monkeypatch):
    e = FakeEngine()
    monkeypatch.setattr(e, "retrieve", lambda *a, **k: [])
    r = e.abstain_check("q", "/tmp/adv")
    assert r.abstain is True and r.max_score == 0.0
