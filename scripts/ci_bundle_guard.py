#!/usr/bin/env python3
"""Fail-closed гард: дан список путей (по одному в строке), которые ПОПАЛИ БЫ в .mcpb-бандл,
exit!=0 если любой forbidden (секрет/копирайт/личное) путь присутствует. Ноль сети, ноль зависимостей."""
import sys, fnmatch

FORBIDDEN = [
    ".env", "*.log", "mcp.json", "board_config.json", "gov_heads.local.json",
    "principis.md", "relationship.md",
    "reference-library-raw/*", "reference-library/*", "*-raw/*",
    "principis_corpus/*", "council/*", "decisions/*", "consults/*", ".consilium/*",
    "advisors/*/build/*", "advisors/*/sources/*", "advisors/*/corpus.jsonl", "advisors/*/corpus.lock.json",
    "lenses/*/build/*", "lenses/*/sources/*",
    "data/embeddings*.npy", "data/embeddings*.meta.json", "scripts/golden/*",
]
ALLOW = ["advisors/machiavelli/corpus.jsonl", "advisors/marcus-aurelius/corpus.jsonl",
         "advisors/sun-tzu/corpus.jsonl"]

def offending(paths):
    bad = []
    for p in paths:
        p = p.strip()
        while p.startswith("./"):
            p = p[2:]
        if not p or p in ALLOW:
            continue
        if any(fnmatch.fnmatch(p, pat) for pat in FORBIDDEN):
            bad.append(p)
    return bad

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    lines = (open(src, encoding="utf-8") if src != "-" else sys.stdin).read().splitlines()
    bad = offending(lines)
    if bad:
        print("BUNDLE GUARD FAIL — forbidden paths would be packed:", *bad, sep="\n  ")
        sys.exit(1)
    print("bundle-guard: OK")
