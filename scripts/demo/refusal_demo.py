#!/usr/bin/env python3
"""Демо `<10 сек`: «докажет цитату — или откажется блефовать».

Единственный кадр, которого нет ни у одного конкурента (см. docs/demo/demo-scenario.md):
не «N мнений спорят», а ЧЕСТНЫЙ ОТКАЗ вложить в уста фигуры выдуманную цитату + дословный
🔵-пруф реальной. Вердикты берутся из ЖИВОГО гейта верности (mcp_server._fidelity_check по
корпусу советника) на КАЖДОМ запуске — не хардкод. Если корпус не может подтвердить 🔵 у
реальной строки или пропускает выдуманную, скрипт падает: демо не может стать сфейканным.

Запуск (живьём / под запись VHS):   python3 scripts/demo/refusal_demo.py
Проверка без анимации (тесты/рендер): python3 scripts/demo/refusal_demo.py --check

Показываем только PD-фигуру (Марк Аврелий, «Размышления» — общественное достояние). Реальные
личные заседания в демо не попадают (приватность). Ноль технического шума: ни JSON, ни путей,
ни тир-кодов — только человекочитаемый вердикт и подлинный источник (Rule 1/10).
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)

ADVISOR_DIR = os.path.join("advisors", "marcus-aurelius")

# Реальная дословная строка из «Размышлений» (Long, Project Gutenberg) — открытие книги I.
REAL_QUOTE = ("Of my grandfather Verus I have learned to be gentle and meek, "
              "and to refrain from all anger and passion.")
# Правдоподобная выдумка в «стоическом» тоне на современную тему — то, что LLM охотно
# припишет Аврелию. В тексте II века её быть не может.
FAKE_QUOTE = "Price your SaaS by the value it creates, not by the cost of your labour."

# Человеческая подпись источника (тот же файл, что вернёт гейт; сверяем ниже).
_SOURCE_LABEL = "Размышления, пер. George Long"


def verdicts():
    """Прогоняет ОБА кандидата через живой гейт верности. Возвращает (real_fc, fake_fc).

    Fail-closed: если корпуса нет, реальная строка не даёт 🔵, или выдумка проходит как
    дословная — поднимаем ошибку. Демо отражает поведение гейта, а не заранее вписанный текст."""
    os.chdir(_ROOT)
    import mcp_server as m
    if not os.path.isdir(ADVISOR_DIR):
        raise SystemExit(
            "Нет корпуса советника (%s). Собери PD-совет: python3 scripts/board.py seed-council"
            % ADVISOR_DIR)
    real = m._fidelity_check(REAL_QUOTE, ADVISOR_DIR)
    fake = m._fidelity_check(FAKE_QUOTE, ADVISOR_DIR)
    if not (real.get("status") == "🔵" and real.get("verbatim")):
        raise SystemExit("Гейт не подтвердил 🔵 у реальной строки — корпус не собран/стар. "
                         "Пересобери: python3 scripts/board.py build-advisor %s" % ADVISOR_DIR)
    if fake.get("verbatim"):
        raise SystemExit("Гейт пропустил выдуманную цитату как дословную — демо недостоверно.")
    if "meditations" not in (real.get("source") or "").lower():
        raise SystemExit("Источник 🔵 не из «Размышлений» — проверь корпус.")
    return real, fake


# ── язык кадра (RU дефолт для рус. витрины; EN — для README.en / Show HN) ──
# Цитаты (реальная/выдуманная) — англ. текст в обоих языках (фигура англоязычна по корпусу).
# Различается только повествование и подпись источника. CTA без длинного тире (AI-маркер).
_LANG = {
    "ru": {
        "figure": "Марк Аврелий",
        "attributed": "ИИ приписал ему цитату:",
        "refuse": "  ⛔ Этого нет в его текстах. Я не вложу ему в уста чужие слова.",
        "caveat": "     Честно: 🟡 в лучшем случае моё прочтение, не его голос.",
        "actual": "А вот что он писал на самом деле:",
        "proof": "  🔵 Сверено слово-в-слово. Размышления, пер. George Long.",
        "cta": "Совет, который докажет цитату или честно промолчит.",
    },
    "en": {
        "figure": "Marcus Aurelius",
        "attributed": "An AI attributed this quote to him:",
        "refuse": "  ⛔ Not in his texts. I will not put words in his mouth.",
        "caveat": "     Honest 🟡: my reading at best, not his own voice.",
        "actual": "Here is what he actually wrote:",
        "proof": "  🔵 Verified word-for-word. Meditations, tr. George Long.",
        "cta": "A council that proves its quotes, or honestly stays silent.",
    },
}


# ── стили строк транскрипта (для анимации и для рендера кадров) ──
def transcript(include_prompt=True, lang="ru"):
    """Упорядоченные строки демо: (style, text). style ∈ prompt|dim|quote|refuse|proof|cta|blank.

    include_prompt=False — когда команду печатает сам рекордер (VHS), чтобы не было двойного промпта.
    lang ∈ {ru,en} — повествование; цитаты и вердикт (из живого гейта) одинаковы."""
    verdicts()  # валидирует гейт (падает при недостоверности) до отрисовки
    s = _LANG[lang]
    lines = []
    if include_prompt:
        lines.append(("prompt", "$ consilium verify %s" % s["figure"]))
    lines += [
        ("blank", ""),
        ("dim", s["attributed"]),
        ("quote", "  «Price your SaaS by the value it creates,"),
        ("quote", "   not by the cost of your labour.»"),
        ("refuse", s["refuse"]),
        ("dim", s["caveat"]),
        ("blank", ""),
        ("dim", s["actual"]),
        ("quote", "  «Of my grandfather Verus I have learned to be gentle and meek,"),
        ("quote", "   and to refrain from all anger and passion.»"),
        ("proof", s["proof"]),
        ("blank", ""),
        ("cta", s["cta"]),
    ]
    return lines


# ── ANSI для живого прогона (тёмная тема, крупный акцент) ──
_ANSI = {
    "prompt": "\033[1;37m",   # белый жирный
    "dim": "\033[2;37m",      # приглушённый серый
    "quote": "\033[0;36m",    # голубой — текст цитаты
    "refuse": "\033[1;33m",   # жёлтый — отказ (дифференциатор)
    "proof": "\033[1;36m",    # ярко-голубой — 🔵 пруф
    "cta": "\033[1;37m",
    "blank": "",
}
_RESET = "\033[0m"


def _type(text, style, char_delay, line_pause):
    color = _ANSI.get(style, "")
    if style == "prompt":  # печатаем посимвольно — эффект набора команды
        sys.stdout.write(color)
        for ch in text:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(char_delay)
        sys.stdout.write(_RESET + "\n")
    else:
        sys.stdout.write(color + text + _RESET + "\n")
    sys.stdout.flush()
    time.sleep(line_pause)


def play(animate=True, include_prompt=True, lang="ru"):
    lines = transcript(include_prompt=include_prompt, lang=lang)
    if not animate:
        for _, text in lines:
            print(text)
        return
    for i, (style, text) in enumerate(lines):
        # паузы подобраны под ≤10 сек: дольше держим кадр отказа и 🔵-пруфа
        pause = 0.05 if style == "blank" else 0.55
        if style == "refuse":
            pause = 1.4          # дифференциатор — держим дольше
        elif style == "proof":
            pause = 1.6
        elif style == "cta":
            pause = 1.2
        _type(text, style, char_delay=0.028, line_pause=pause)


def main(argv):
    if "--check" in argv:
        real, fake = verdicts()
        print("REAL -> %s verbatim=%s source=%s" % (real["status"], real["verbatim"], real["source"]))
        print("FAKE -> %s verbatim=%s" % (fake["status"], fake["verbatim"]))
        return 0
    lang = "en" if "--en" in argv else "ru"
    play(animate="--no-anim" not in argv, include_prompt="--no-prompt" not in argv, lang=lang)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
