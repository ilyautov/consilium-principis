"""Отчёт: какой tier ретрива доступен на этой машине. Помогает «0-install юзеру»
понять, что у него есть, без чтения кода."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/ — engine это пакет


def report():
    from engine.semantic import SemanticEngine
    from engine import load_config_value
    sem = SemanticEngine.available()
    mode = load_config_value("retrieval_mode", "auto")
    if sem:
        tier = "FULL — hybrid (semantic ∪ lexical, RRF)" if mode == "hybrid" else "FULL (semantic, bge-m3)"
    else:
        tier = "SIMPLE (lexical floor)"
    print("Consilium-Principis — диагностика движка")
    print(f"  ollama/bge-m3 (semantic): {'✓ доступен' if sem else '✗ нет'}")
    print(f"  → активный tier: {tier}")
    if not sem:
        print("  fidelity-контур: ✓ работает и на полу (verbatim-чек не требует ollama)")
        print("  поднять до FULL: запустить ollama + `ollama pull bge-m3`, затем build_index")


if __name__ == "__main__":
    report()
