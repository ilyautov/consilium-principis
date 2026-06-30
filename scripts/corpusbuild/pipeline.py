"""Оркестратор сборки: ingest → clean → chunk по всем источникам → build/corpus.jsonl + lock."""
import os, json
from . import ingest, clean, chunk as chunkmod, buildlock, paths

SUPPORTED = (".txt", ".md", ".pdf", ".epub")


def _is_tier_mode(source: str, advisor_dir: str) -> bool:
    from engine import provenance as prov
    man = prov.load_manifest(advisor_dir) or {}
    return ((man.get(source) or {}).get("apparatus") or {}).get("mode") == "tier"


def build(advisor_dir: str, config=None, built_at: str = "unknown"):
    config = config or {}
    chunk_cfg = config.get("chunk", {})
    src_dir = os.path.join(advisor_dir, "sources")
    all_chunks = []
    for fn in sorted(os.listdir(src_dir)):
        if os.path.splitext(fn)[1].lower() not in SUPPORTED:
            continue
        recs = ingest.extract_source(os.path.join(src_dir, fn))
        if _is_tier_mode(fn, advisor_dir):           # apparatus tier → секции+инлайн одним проходом
            tagged = clean.apparatus_tier(recs, fn, advisor_dir)
        else:
            tagged = clean.tag_regions(recs, fn, advisor_dir)
        all_chunks.extend(chunkmod.chunk_records(tagged, fn, chunk_cfg))
    os.makedirs(paths.build_dir(advisor_dir), exist_ok=True)
    out = os.path.join(paths.build_dir(advisor_dir), "corpus.jsonl")  # пишем ВСЕГДА в build/
    with open(out, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    buildlock.write_lock(advisor_dir, config, all_chunks, built_at)
    return all_chunks  # corpus_path() теперь автоматически отдаёт build/corpus.jsonl
