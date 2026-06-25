import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import doctor

def _corpus(adv, rows):
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def test_doctor_flags_unlabeled_A(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "x", "tier": "A", "text": "?"}, {"source": "y", "tier": "P1", "text": "ok"}])
    rep = doctor.report(adv)
    assert rep["tiers"]["A"] == 1
    assert rep["ok"] is False  # неразмеченное (A) валит гейт

def test_doctor_ok_when_all_labeled(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "y", "tier": "P1", "text": "ok"}, {"source": "z", "tier": "S1", "text": "comm"}])
    rep = doctor.report(adv)
    assert rep["ok"] is True and rep["tiers"] == {"P1": 1, "S1": 1}
