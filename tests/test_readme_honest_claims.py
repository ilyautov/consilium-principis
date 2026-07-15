"""Гард: витрины НЕ оверклеймят «работает офлайн» и прочее. Ров = строгость, клеймы честные.

Офлайн только КОНТУР честности (гейт/сверка/поиск до чистого Python). РАССУЖДЕНИЕ советников
крутится на хост-модели (в Claude Code — облако). Значит любое упоминание «офлайн» в README
должно быть заужено квалификатором, а не выдаваться за свойство всего продукта.

ДВА ФАЙЛА, ДВА ЯЗЫКА. `README.md` — английский (его показывает GitHub), `README.ru.md` — русский.
Каждая проверка идёт по ОБОИМ и несёт паттерны на ОБОИХ языках: иначе после свопа языков
русскоязычные проверки позеленели бы, не проверив ничего, а второй файл остался бы без охраны
(«код есть» ≠ «код исполняется» — в этом проекте это ловили дважды). Стережёт это
`test_guard_is_not_asleep` ниже: он скармливает каждому чекеру канарейку и требует срабатывания.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README_EN = ROOT / "README.md"  # витрина GitHub — английский по умолчанию
README_RU = ROOT / "README.ru.md"
READMES = (README_EN, README_RU)

# Оверклейм механизма верности: гейт делает НОРМАЛИЗОВАННЫЙ verbatim-матч (регистр/пунктуация/
# пробелы игнорируются, substring по корпусу) — это «дословно / слово-в-слово / word-for-word»,
# НЕ «посимвольно» и тем более не «побайтно». Слова автора дословны (не пересказ) — правда и это
# ров; но «character-by-character / byte-exact» сильнее реального механизма.
CHAR_EXACT_OVERCLAIM = (
    "посимвольн", "побайтн",
    "character-by-character", "char-by-char", "byte-by-byte", "byte-exact",
)

# Неквалифицированный whole-product claim: офлайн выдан за свойство ВСЕГО продукта.
# Рассуждение советников облачное — так писать нельзя ни на одном языке.
OFFLINE_OVERCLAIM = (
    "работает офлайн, без ключей",
    "работает оффлайн, без ключей",
    "работает полностью офлайн",
    "работает полностью оффлайн",
    "works offline",
    "runs offline",
    "work offline",
    "fully offline",
    "completely offline",
    "entirely offline",
    "100% offline",
    "offline, no keys",
    "offline and no keys",
)

# Квалификаторы, рядом с которыми упоминание офлайна честно (в той же строке).
# RU: «контур», «локальные модели», «агент, который у тебя уже есть», «оффлайн-сьют» (свойство
# тест-сьюта/CI, не продукта). EN-зеркало: contour / local / gate / loop / suite.
QUALIFIERS = (
    "контур", "локальн", "агент, который у тебя уже есть", "сьют",
    "contour", "local", "gate", "loop", "suite",
)

# Написания «офлайн» на обоих языках (RU-вариант с двумя «ф» — тоже ловим, иначе дыра).
OFFLINE_MENTIONS = ("офлайн", "оффлайн", "offline")

# Бейдж-строка не должна утверждать «works offline» (вводит в заблуждение).
BADGE_OFFLINE_CLAIM = ("works-offline", "works offline", "works%20offline")

# Недоказанные claim'ы про анти-сикофантику как ИЗМЕРЕННЫЙ эффект. Наш собственный probe
# (n=24, bootstrap-CI) дал ЧИСТЫЙ НОЛЬ — мягкий prompt-нудж не двигает поведение. Значит на
# витрине НЕ заявляем «остановит ошибку / скорее оспорит / не поддакнет» как факт: формулируем
# как структурное РАЗНООБРАЗИЕ линз (это держится на дискриминативности кернелов), не как
# проверенный анти-лесть-эффект на юзера. EN-список — смысловое зеркало RU.
UNPROVEN_ANTISYC = (
    # RU
    "скорее оспорит, чем поддакнет",
    "остановит твою ошибку",
    "остановит вашу ошибку",
    "не даст тебе ошибиться",
    "не даст вам ошибиться",
    "не поддакивает",
    # EN — «не поддакнет»
    "will not flatter",
    "won't flatter",
    "does not flatter",
    "doesn't flatter",
    "never flatters",
    "no flattery",
    "no yes-men",
    # EN — «скорее оспорит, чем поддакнет»
    "pushes back instead of agreeing",
    "pushes back rather than agreeing",
    "more likely to push back than agree",
    "will push back rather than agree",
    "won't just agree",
    "will not just agree",
    # EN — «остановит твою ошибку / не даст ошибиться»
    "stops your mistake",
    "will stop your mistake",
    "stops you from making a mistake",
    "keeps you from making a mistake",
    "won't let you make a mistake",
    "will not let you make a mistake",
)


def _flatten(text):
    """Схлопывает пробелы/переносы в одну строку + карта «позиция → номер строки».

    EN-README жёстко перенесён по ~100 символов, поэтому фраза («checked ... word-for-word»)
    легко разрывается переносом. Плоский поиск ловит её надёжно, а карта возвращает строку
    для внятного сообщения об ошибке.
    """
    flat, linemap = [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        norm = " ".join(raw.split())
        if not norm:
            continue
        if flat:
            flat.append(" ")
            linemap.append(lineno)
        flat.append(norm)
        linemap.extend([lineno] * len(norm))
    return "".join(flat).lower(), linemap


def _find_phrases(text, phrases):
    """[(номер строки, фраза)] для каждого вхождения любой из phrases (регистронезависимо)."""
    flat, linemap = _flatten(text)
    hits = []
    for phrase in phrases:
        needle = " ".join(phrase.split()).lower()
        start = flat.find(needle)
        while start != -1:
            hits.append((linemap[start], phrase))
            start = flat.find(needle, start + 1)
    return hits


def _check_offline_overclaim(text):
    return _find_phrases(text, OFFLINE_OVERCLAIM)


def _check_badge_offline(text):
    return _find_phrases(text, BADGE_OFFLINE_CLAIM)


def _check_char_exact(text):
    return _find_phrases(text, CHAR_EXACT_OVERCLAIM)


def _check_unproven_antisyc(text):
    return _find_phrases(text, UNPROVEN_ANTISYC)


def _check_unqualified_offline(text):
    """Каждая прозаическая строка с «офлайн»/«offline» несёт квалификатор в ТОЙ ЖЕ строке."""
    hits = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        low = raw.lower()
        if "shields.io" in low:  # бейдж-картинки покрыты отдельным чекером
            continue
        if any(m in low for m in OFFLINE_MENTIONS):
            if not any(q in low for q in QUALIFIERS):
                hits.append((lineno, raw.strip()))
    return hits


# Реестр: имя → (чекер, канарейка-триггер, хвост сообщения).
# Канарейка обязана ронять свой чекер — этим test_guard_is_not_asleep доказывает, что гард
# исполняется, а не просто существует.
CHECKERS = {
    "offline_overclaim": (
        _check_offline_overclaim,
        "Works offline, no keys needed.",
        "офлайн выдан за свойство всего продукта — рассуждение советников облачное",
    ),
    "badge_offline": (
        _check_badge_offline,
        "![works offline](https://img.shields.io/badge/works%20offline-success)",
        "бейдж утверждает 'works offline' — оставь честный (no extra keys · no extra cost)",
    ),
    "unqualified_offline": (
        _check_unqualified_offline,
        "The board runs offline for everyone.",
        "неквалифицированное упоминание офлайна — заузь на контур/локальные модели "
        f"(квалификаторы: {', '.join(QUALIFIERS)})",
    ),
    "char_exact": (
        _check_char_exact,
        "Every quote is verified character-by-character.",
        "оверклейм механизма верности: гейт делает нормализованный verbatim — "
        "формулируй «дословно / слово-в-слово / word-for-word»",
    ),
    "unproven_antisyc": (
        _check_unproven_antisyc,
        "The board will not flatter you.",
        "анти-сикофантика заявлена как проверенный эффект (probe n=24 = ЧИСТЫЙ НОЛЬ) — "
        "формулируй как структурное РАЗНООБРАЗИЕ линз",
    ),
}


def _run(name):
    """Прогоняет чекер по ОБОИМ витринам, собирает нарушения с файлом и строкой."""
    checker, _, hint = CHECKERS[name]
    offenders = [
        f"{path.name}:{lineno}: {found}"
        for path in READMES
        for lineno, found in checker(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, hint + "\n  " + "\n  ".join(offenders)


def test_no_whole_product_offline_overclaim():
    _run("offline_overclaim")


def test_badge_does_not_claim_offline():
    _run("badge_offline")


def test_every_offline_mention_is_qualified():
    _run("unqualified_offline")


def test_no_char_exact_fidelity_overclaim():
    _run("char_exact")


def test_no_unproven_antisycophancy_overclaim():
    _run("unproven_antisyc")


# --- Гард не спит -----------------------------------------------------------------
# Пустой/пропавший файл или чекер, потерявший предмет проверки, обязан РОНЯТЬ сьют,
# а не молча зеленеть. Здесь это ловится напрямую.

def test_both_readmes_exist_and_are_substantial():
    """Витрина не должна пропасть/опустеть: тогда все проверки выше стали бы вакуумными."""
    for path in READMES:
        assert path.is_file(), f"{path.name} пропал — проверки честности стали вакуумными"
        assert len(path.read_text(encoding="utf-8")) > 2000, (
            f"{path.name} подозрительно пуст ({path.stat().st_size} байт) — гард нечего охранять"
        )


def test_readme_languages_are_not_swapped():
    """README.md английский (витрина GitHub), README.ru.md русский.

    Если языки поменять местами, паттерны формально отработают, но по факту будут искать
    RU-фразы в EN-тексте. Гард должен заметить это, а не позеленеть.
    """

    def cyrillic_share(path):
        text = path.read_text(encoding="utf-8")
        letters = [c for c in text if c.isalpha()]
        assert letters, f"{path.name}: ни одной буквы"
        return sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / len(letters)

    en_share = cyrillic_share(README_EN)
    ru_share = cyrillic_share(README_RU)
    assert en_share < 0.10, (
        f"README.md должен быть АНГЛИЙСКИМ (витрина GitHub), а кириллицы в нём {en_share:.0%}"
    )
    assert ru_share > 0.50, (
        f"README.ru.md должен быть РУССКИМ, а кириллицы в нём всего {ru_share:.0%}"
    )


def test_every_checker_fires_on_its_canary():
    """Каждый чекер ловит свою канарейку — доказательство, что гард исполняется.

    Это ответ на «код есть ≠ код исполняется»: если чекер разучится ловить (сломан regex,
    вычищен список паттернов, промазали с языком) — падает здесь, а не молчит на витрине.
    """
    for name, (checker, canary, _) in CHECKERS.items():
        assert checker(canary), f"чекер {name} НЕ СРАБОТАЛ на своей канарейке: {canary!r}"


def test_checkers_are_silent_on_benign_text():
    """Обратная сторона: чекер не срабатывает на честном тексте (иначе он бесполезно шумит)."""
    benign = (
        "The honesty contour needs no network.\n"
        "Full offline is available only with local models.\n"
        "Every quote is verified word-for-word against the author's corpus.\n"
        "Разные линзы, а не хор: советники держат свои углы.\n"
    )
    for name, (checker, _, _) in CHECKERS.items():
        assert not checker(benign), f"чекер {name} ложно сработал на честном тексте"


def test_canaries_are_bilingual_across_the_pattern_lists():
    """Паттерны обязаны быть на ОБОИХ языках: RU-only списки — это спящий гард.

    После свопа языков (README.md стал английским) чисто русские паттерны позеленели бы,
    не проверив ничего. Требуем присутствия и латиницы, и кириллицы в каждом списке.
    """
    lists = {
        "OFFLINE_OVERCLAIM": OFFLINE_OVERCLAIM,
        "QUALIFIERS": QUALIFIERS,
        "OFFLINE_MENTIONS": OFFLINE_MENTIONS,
        "CHAR_EXACT_OVERCLAIM": CHAR_EXACT_OVERCLAIM,
        "UNPROVEN_ANTISYC": UNPROVEN_ANTISYC,
    }
    for name, patterns in lists.items():
        joined = "".join(patterns).lower()
        assert any("a" <= c <= "z" for c in joined), f"{name}: нет ни одного EN-паттерна"
        assert any("а" <= c <= "я" or c == "ё" for c in joined), f"{name}: нет ни одного RU-паттерна"
