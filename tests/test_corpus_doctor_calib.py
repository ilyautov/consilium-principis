import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import doctor

def _build(adv, corpus_rows, kernels=None, enrich=None):
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in corpus_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if kernels is not None:
        json.dump(kernels, open(os.path.join(adv, "build", "kernels.json"), "w"))
    if enrich is not None:
        with open(os.path.join(adv, "build", "enrichment.jsonl"), "w", encoding="utf-8") as f:
            for r in enrich:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

def test_calibration_flags_groundless_kernel(tmp_path):
    adv = str(tmp_path)
    _build(adv, [{"source": "p", "tier": "P1", "text": "ok"}],
           kernels=[{"name": "K", "grounded_in": []}])
    rep = doctor.calibration(adv)
    assert rep["groundless_kernels"] == 1 and rep["ok"] is False

def test_calibration_flags_crossdomain_without_trace(tmp_path):
    adv = str(tmp_path)
    _build(adv, [{"source": "p", "tier": "P1", "text": "ok"}],
           enrich=[{"kind": "кросс-домен", "text": "t", "derived_from": ["p:1-1"], "tier": "derived"}])
    rep = doctor.calibration(adv)
    assert rep["untraced_cross_domain"] == 1 and rep["ok"] is False

def test_calibration_ok_when_clean(tmp_path):
    adv = str(tmp_path)
    _build(adv, [{"source": "p", "tier": "P1", "text": "ok"}],
           kernels=[{"name": "K", "grounded_in": ["p:1-1"]}],
           enrich=[{"kind": "пример", "text": "t", "derived_from": ["p:1-1"], "tier": "derived"}])
    assert doctor.calibration(adv)["ok"] is True
