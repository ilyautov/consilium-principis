import re, glob, os
def test_no_raw_corpus_jsonl_literals():
    bad = []
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "scripts", "**", "*.py"), recursive=True):
        if os.path.basename(f) in ("paths.py", "pipeline.py"):  # резолвер/писатель — можно
            continue
        src = open(f, encoding="utf-8").read()
        if re.search(r'["\']corpus\.jsonl["\']', src) and "corpus_path" not in src:
            bad.append(os.path.relpath(f))
    assert not bad, f"эти файлы читают corpus.jsonl мимо резолвера: {bad}"
