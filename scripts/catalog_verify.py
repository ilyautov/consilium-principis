#!/usr/bin/env python3
"""catalog_verify.py — ритуал целостности PD-каталога. Обходит записи, сверяет подпись/PD-basis.
  python scripts/catalog_verify.py            # проверить (fail на дрейфе → exit 1)
  python scripts/catalog_verify.py --seed     # посеять/обновить sha256 (нужна сеть)"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog, collect_common as cc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="записать sha256 в каждую запись (нужна сеть)")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    a = ap.parse_args()
    rep = catalog.verify_catalog(os.path.abspath(a.root), fetch=cc.fetch, seed=a.seed)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    sys.exit(0 if rep["ok"] else 1)

if __name__ == "__main__":
    main()
