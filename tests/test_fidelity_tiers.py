import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from engine import fidelity

def _corpus(adv, rows):
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def test_quote_in_p1_is_blue_eligible(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "prince.txt", "tier": "P1", "text": "it is safer to be feared than loved"}])
    assert fidelity.tier_of_match("safer to be feared than loved", adv) == "P1"

def test_quote_only_in_s1_is_misattribution(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "tarasov.txt", "tier": "S1", "text": "Тарасов пишет: власть держится на страхе"}])
    assert fidelity.tier_of_match("власть держится на страхе", adv) == "S1"
    assert fidelity.is_blue_eligible("власть держится на страхе", adv) is False

def test_quote_absent_returns_none(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "p.txt", "tier": "P1", "text": "something else entirely"}])
    assert fidelity.tier_of_match("nonexistent phrase", adv) is None
