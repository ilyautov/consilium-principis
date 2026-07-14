#!/usr/bin/env python3
"""Демо C: спросил по-русски — 🔵 по английскому тексту.

Вопрос на русском, корпус фигуры английский. Совет переводит запрос в язык корпуса
(это его ризонинг, автоперевода в коде нет — честно) и находит строку; КОД сверяет её
дословно против корпуса → 🔵 с источником. Код-бэкед тут именно сверка (fail-closed:
если строка не 🔵, скрипт падает); перевод — работа совета, не гарантия кода.

Запуск:  python3 scripts/demo/crosslingual_demo.py [--en] [--no-prompt] [--no-anim] [--check]
Вопрос всегда русский (в этом суть кросс-языка); --en меняет только повествование.
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
RU_QUESTION = "Что Аврелий говорил о гневе?"
EN_QUERY = "anger and passion"                       # перевод, который дал бы совет
# Дословная строка «Размышлений» про гнев — якорь сверки.
LINE = "and to refrain from all anger and passion"


def run():
    """Сверяет якорную англ. строку живым гейтом. Возвращает fidelity-объект.

    Fail-closed: строка обязана быть 🔵 дословно со своим источником, иначе SystemExit."""
    os.chdir(_ROOT)
    import mcp_server as m
    if not os.path.isfile(corpus_path(ADVISOR_DIR)):
        raise SystemExit("Нет корпуса (%s). Собери: python3 scripts/board.py seed-council" % ADVISOR_DIR)
    fc = m._fidelity_check(LINE, ADVISOR_DIR)
    if not (fc.get("status") == "🔵" and fc.get("verbatim")):
        raise SystemExit("Якорная строка не 🔵 — корпус не собран/стар, демо недостоверно.")
    return fc


_LANG = {
    "ru": {
        "prompt": "$ consilium ask «%s»" % RU_QUESTION,
        "setup": "Вопрос по-русски. Корпус Аврелия английский.",
        "translate": "Совет переводит запрос в язык корпуса (это его работа):",
        "arrow": "  → «%s»" % EN_QUERY,
        "label": "Марк Аврелий  🔵",
        "proof": "  Сверено слово-в-слово. Размышления, пер. George Long.",
        "cta": "Язык любой, верность та же. Ни строки мимо оригинала.",
    },
    "en": {
        "prompt": "$ consilium ask «%s»" % RU_QUESTION,
        "setup": "The question is in Russian. Aurelius's corpus is English.",
        "translate": "The council translates the query into the corpus language (its own job):",
        "arrow": "  → «%s»" % EN_QUERY,
        "label": "Marcus Aurelius  🔵",
        "proof": "  Verified word-for-word. Meditations, tr. George Long.",
        "cta": "Any language in, the same fidelity out. Not one line off the original.",
    },
}


def transcript(include_prompt=True, lang="ru"):
    run()                                            # валидирует до отрисовки
    s = _LANG[lang]
    lines = []
    if include_prompt:
        lines.append(("prompt", s["prompt"]))
    lines += [
        ("blank", ""),
        ("dim", s["setup"]),
        ("dim", s["translate"]),
        ("quote", s["arrow"]),
        ("blank", ""),
        ("label", s["label"]),
        ("quote", "  «...to refrain from all anger and passion»"),
        ("proof", s["proof"]),
        ("blank", ""),
        ("cta", s["cta"]),
    ]
    return lines


def main(argv):
    if "--check" in argv:
        fc = run()
        print("LINE -> %s verbatim=%s source=%s" % (fc["status"], fc["verbatim"], fc["source"]))
        return 0
    lang = "en" if "--en" in argv else "ru"
    _harness.render(transcript(include_prompt="--no-prompt" not in argv, lang=lang),
                    animate="--no-anim" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
