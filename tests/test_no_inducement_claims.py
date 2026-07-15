"""Гард: публичные витрины НЕ подстрекают к клонированию личности (доктрина inducement, Grokster).

Рычаг 2 правовой позиции «движок, не распространитель» (docs/dev/legal-posture-2026-07): даже
нейтральный инструмент ловит ответственность, если МАРКЕТИНГ активно поощряет нарушение. Значит:
  ✅ «Принеси свой легально-полученный корпус» / bring-your-own-corpus / линза на PD-текстах.
  ❌ «Склонируй любимого живого автора из его книг» / clone anyone / «цифровая копия личности».

Две проверки (мирроринг honesty-гарда test_readme_honest_claims):
  1. Ни одной inducement-фразы БЕЗ негатора в той же строке (дисклеймер «не «клонируй кого угодно»»
     легитимен — он ОТРИЦАЕТ подстрекательство; голое «клонируй кого угодно» — нет).
  2. Каждая публичная витрина несёт affirmative-границу «движок, не распространитель».
Точные person-clone фразы, чтобы НЕ ловить софт-clone («git clone», «склонирует репозиторий»).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DOCS = [
    ROOT / "README.md",  # витрина GitHub — английский
    ROOT / "README.ru.md",
    ROOT / "SKILL.md",
    ROOT / "install-skill" / "SKILL.md",
]

# Подстрекательство к клонированию ЛИЧНОСТИ (не софта). Многословные, чтобы «git clone» /
# «склонирует репозиторий» / «Клонируй в /tmp» не триггерили.
INDUCEMENT = (
    "склонируй любимого",
    "склонируй любого",
    "склонируй живого",
    "клонируй кого угодно",
    "клонируй любого",
    "clone anyone",
    "clone any author",
    "clone any living",
    "clone your favorite",
    "цифровая копия личности",
    "цифровую копию личности",
)

# Негаторы: если inducement-фраза в строке отрицается — это дисклеймер, а не подстрекательство.
NEGATORS = ("не ", "не«", "не \"", "не «", "not ", "without ", "вместо", "≠", "instead of", "rather than")

# Affirmative-граница: каждая витрина должна нести позицию «движок, не распространитель».
BOUNDARY_MARKERS = ("не распространитель", "not a content distributor", "not a distributor")


def test_no_bare_inducement_in_public_docs():
    offenders = []
    for doc in PUBLIC_DOCS:
        for line in doc.read_text(encoding="utf-8").splitlines():
            low = line.lower()
            for phrase in INDUCEMENT:
                if phrase in low and not any(n in low for n in NEGATORS):
                    offenders.append(f"{doc.name}: {line.strip()}")
    assert not offenders, (
        "Публичная витрина подстрекает к клонированию личности (Grokster). Переформулируй как "
        "bring-your-own-corpus / линзу на PD-текстах, либо отрицай явно: "
        + " | ".join(offenders)
    )


def test_public_docs_carry_engine_not_distributor_boundary():
    import re

    missing = []
    for doc in PUBLIC_DOCS:
        # Схлопываем пробелы/переносы: граница «движок, не\n   распространитель» переносится строкой.
        low = re.sub(r"\s+", " ", doc.read_text(encoding="utf-8").lower())
        if not any(m in low for m in BOUNDARY_MARKERS):
            missing.append(doc.name)
    assert not missing, (
        "Публичная витрина без affirmative-границы «движок, не распространитель» "
        "(рычаг 2 no-inducement): " + ", ".join(missing)
    )
