"""Гард: внутренняя записка позиционирования существует и НЕ протекает в публичный README."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, "..", "docs", "dev", "positioning-vs-competitors.md")


def test_positioning_doc_exists_internal():
    assert os.path.exists(DOC), "записка отсутствует"
    t = open(DOC, encoding="utf-8").read().lower()
    assert "provenance" in t or "провенанс" in t or "verified board" in t
    # честная рамка: структурное разногласие не заявлено как доказанное на LLM
    assert "null" in t or "ноль" in t or "не доказан" in t or "unproven" in t
    # внутренняя, не README
    assert "readme" in t  # должен явно оговаривать «не в README»
