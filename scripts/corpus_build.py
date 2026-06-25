#!/usr/bin/env python3
"""CLI сборщика корпуса. build по умолчанию; --report — только доктор."""
import sys, os, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from corpus import pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisor_dir")
    ap.add_argument("--report", action="store_true", help="только валидационный доктор")
    args = ap.parse_args()
    from corpus import doctor  # ленивый импорт: модуль доктора появляется в Task 10
    if args.report:
        doctor.report(args.advisor_dir); return
    built_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    chunks = pipeline.build(args.advisor_dir, built_at=built_at)
    print(f"собрано чанков: {len(chunks)} → {args.advisor_dir}/build/corpus.jsonl")
    doctor.report(args.advisor_dir)


if __name__ == "__main__":
    main()
