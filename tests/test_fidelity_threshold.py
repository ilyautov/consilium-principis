"""H2 (Правило A): порог верифицированной цитаты — по СЛОВАМ (≥3), не по символам.
Одиночное/двухсловное совпадение дословно найдётся, но как «цитата» бессмысленно
и вводит в заблуждение (напр. «remember»). Ниже порога слов → None (🟡, fail-closed).
См. внутренний план ремедиации (PHASE 2 / Task 2.1)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_single_word_not_blue(tmp_path):
    from engine.fidelity import best_match
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text(
        '{"text":"remember your mortality every single day","tier":"P1"}\n',
        encoding="utf-8",
    )
    assert best_match("remember", str(adv)) is None                    # 1 слово → не 🔵
    assert best_match("your mortality", str(adv)) is None               # 2 слова → не 🔵
    assert best_match("remember your mortality", str(adv)) is not None  # 3 слова → ок
