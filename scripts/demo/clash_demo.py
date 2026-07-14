#!/usr/bin/env python3
"""Демо «клэш совета» (ИЛЛЮСТРАТИВНЫЙ, с честной пометкой).

Разные линзы расходятся. ВАЖНО про честность: доводы советников (🟡) генерит хост-LLM,
код их НЕ верифицирует — это прочтение модели линзой автора, а не сверенные слова. Чтобы
демо не стало театром «N мнений спорят» (от которого мы отстраиваемся), в кадре стоит
пометка, а ОДНА дословная строка (🔵) сверяется живым гейтом верности (fail-closed): если
она не 🔵, скрипт падает. Так даже иллюстрация несёт проверяемое ядро.

Запуск:  python3 scripts/demo/clash_demo.py [--en] [--no-prompt] [--no-anim] [--check]
Все фигуры — public-domain (Сунь-цзы, Макиавелли, Аврелий).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _HERE)

import _harness
from corpusbuild.paths import corpus_path

ADVISOR_DIR = os.path.join("advisors", "marcus-aurelius")
# Дословная строка «Размышлений» про «делать настоящее дело целиком» — единственное
# проверяемое ядро иллюстрации (та же строка, что на витрине).
BLUE_LINE = ("Let it be thy earnest and incessant care as a Roman and a man "
             "to perform whatsoever it is that thou art about")


def run():
    """Сверяет 🔵-строку живым гейтом (fail-closed). Возвращает fidelity-объект."""
    os.chdir(_ROOT)
    import mcp_server as m
    if not os.path.isfile(corpus_path(ADVISOR_DIR)):
        raise SystemExit("Нет корпуса (%s). Собери: python3 scripts/board.py seed-council" % ADVISOR_DIR)
    fc = m._fidelity_check(BLUE_LINE, ADVISOR_DIR)
    if not (fc.get("status") == "🔵" and fc.get("verbatim")):
        raise SystemExit("🔵-строка иллюстрации не сверилась — демо недостоверно.")
    return fc


_LANG = {
    "ru": {
        "prompt": "$ consilium «тяну четыре направления. на чём сфокусироваться?»",
        "sun_label": "Сунь-цзы · линза «Стратег»  🟡",
        "sun": "  Кто силён везде, не силён нигде. Держи фронт с перевесом, прочее малым.",
        "mac_label": "Макиавелли  🟡",
        "mac": "  Вопрос не «что развивать», а «от чего готов отказаться». Это и есть выбор.",
        "aur_label": "Марк Аврелий  🔵",
        "note1": "🟡 доводы: прочтение модели линзой автора, не сверенные слова.",
        "note2": "Проверяется только 🔵. Пример иллюстративен.",
        "cta": "Совет спорит, но не блефует.",
    },
    "en": {
        "prompt": "$ consilium «I'm juggling four directions. where do I focus?»",
        "sun_label": "Sun Tzu · «Strategist» lens  🟡",
        "sun": "  Strong everywhere is strong nowhere. Hold where you lead, starve the rest.",
        "mac_label": "Machiavelli  🟡",
        "mac": "  Not «what to grow» but «what to give up». That is the decision.",
        "aur_label": "Marcus Aurelius  🔵",
        "note1": "🟡 arguments are the model's reading through the author's lens, not verified.",
        "note2": "Only 🔵 is checked against the corpus. This example is illustrative.",
        "cta": "The council argues, but it does not bluff.",
    },
}


def transcript(include_prompt=True, lang="ru"):
    run()                                            # валидирует 🔵-ядро до отрисовки
    s = _LANG[lang]
    lines = []
    if include_prompt:
        lines.append(("prompt", s["prompt"]))
    lines += [
        ("blank", ""),
        ("label", s["sun_label"]),
        ("dim", s["sun"]),
        ("label", s["mac_label"]),
        ("dim", s["mac"]),
        ("label", s["aur_label"]),
        ("quote", "  «Let it be thy earnest and incessant care as a Roman and a man"),
        ("proof", "   to perform whatsoever it is that thou art about» (Meditations)"),
        ("blank", ""),
        ("warn", s["note1"]),
        ("warn", s["note2"]),
        ("cta", s["cta"]),
    ]
    return lines


def main(argv):
    if "--check" in argv:
        fc = run()
        print("BLUE_LINE -> %s verbatim=%s" % (fc["status"], fc["verbatim"]))
        return 0
    lang = "en" if "--en" in argv else "ru"
    _harness.render(transcript(include_prompt="--no-prompt" not in argv, lang=lang),
                    animate="--no-anim" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
