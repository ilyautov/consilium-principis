"""Гард: README не оверклеймит «работает офлайн». Ров = строгость, поэтому клеймы честные.

Офлайн только КОНТУР честности (гейт/сверка/поиск до чистого Python). РАССУЖДЕНИЕ советников
крутится на хост-модели (в Claude Code — облако). Значит любое упоминание «офлайн» в README
должно быть заужено квалификатором, а не выдаваться за свойство всего продукта.
"""
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"

# Квалификаторы, рядом с которыми упоминание офлайна честно (в той же строке).
QUALIFIERS = ("контур", "локальн", "агент, который у тебя уже есть")

# Недоказанные claim'ы про анти-сикофантику как ИЗМЕРЕННЫЙ эффект. Наш собственный probe
# (n=24, bootstrap-CI) дал ЧИСТЫЙ НОЛЬ — мягкий prompt-нудж не двигает поведение. Значит на
# витрине НЕ заявляем «остановит ошибку / скорее оспорит / не поддакнет» как факт: формулируем
# как структурное РАЗНООБРАЗИЕ линз (это держится на дискриминативности кернелов), не как
# проверенный анти-лесть-эффект на юзера.
UNPROVEN_ANTISYC = (
    "скорее оспорит, чем поддакнет",
    "остановит твою ошибку",
    "остановит вашу ошибку",
    "не даст тебе ошибиться",
    "не поддакивает",
)


def _text():
    return README.read_text(encoding="utf-8")


def test_no_whole_product_offline_overclaim():
    """Неквалифицированный whole-product claim «Работает офлайн, без ключей» запрещён."""
    assert "Работает офлайн, без ключей" not in _text(), (
        "README оверклеймит офлайн как свойство всего продукта — рассуждение советников облачное"
    )


def test_badge_does_not_claim_offline():
    """Бейдж-строка не должна утверждать «works offline» (вводит в заблуждение)."""
    low = _text().lower()
    assert "works-offline" not in low and "works offline" not in low, (
        "Бейдж утверждает 'works offline' — убрать, оставить честный (no extra keys · no extra cost)"
    )


def test_every_offline_mention_is_qualified():
    """Каждая прозаическая строка с «офлайн»/«offline» несёт квалификатор в той же строке."""
    offenders = []
    for line in _text().splitlines():
        low = line.lower()
        if "shields.io" in low:  # бейдж-картинки покрыты отдельным тестом
            continue
        if "офлайн" in low or "offline" in low:
            if not any(q in low for q in QUALIFIERS):
                offenders.append(line.strip())
    assert not offenders, (
        "Неквалифицированное упоминание офлайна (заузь на контур/локальные модели/хост): "
        + " | ".join(offenders)
    )


def test_no_unproven_antisycophancy_overclaim():
    """Анти-сикофантику не заявляем как доказанный эффект (probe n=24 = ноль)."""
    low = _text().lower()
    hits = [p for p in UNPROVEN_ANTISYC if p.lower() in low]
    assert not hits, (
        "README заявляет анти-сикофантику как проверенный эффект (probe n=24 = ноль): "
        + ", ".join(hits)
        + ". Формулируй как структурное РАЗНООБРАЗИЕ линз, не как доказанное 'оспорит/не поддакнет'."
    )
