#!/usr/bin/env python3
"""Демо A: «цитата не в тех устах» — код ловит перепутанного автора.

Дифференциатор, которого нет ни у кого: ров сверяет grounded-цитату против корпуса ЕЁ
советника. Одну и ту же реальную строку Аврелия отдаём в двух устах — Макиавелли (чужой
корпус → маркер снят) и самому Аврелию (свой корпус → 🔵 держится). Вердикт считает живой
валидатор mcp_server._validate_session_attribution на каждом прогоне, не хардкод; при
неверном исходе скрипт падает (демо не может стать сфейканным).

Запуск:  python3 scripts/demo/misattribution_demo.py [--en] [--no-prompt] [--no-anim] [--check]
Обе фигуры — public-domain (Аврелий, Макиавелли). Ноль техношума в кадре (Rule 1/10).
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

WRONG_DIR = os.path.join("advisors", "machiavelli")
RIGHT_DIR = os.path.join("advisors", "marcus-aurelius")
# Реальная дословная строка Аврелия (открытие «Размышлений», кн. I).
LINE = ("Of my grandfather Verus I have learned to be gentle and meek, "
        "and to refrain from all anger and passion.")


def run():
    """Гоняет живой валидатор атрибуции. Возвращает (violated_op, kept_op, reason).

    Fail-closed: строка в чужих устах ОБЯЗАНА стать violation, в своих — остаться blue;
    иначе SystemExit (демо отражает поведение кода, а не вписанный текст)."""
    os.chdir(_ROOT)
    import mcp_server as m
    for d in (WRONG_DIR, RIGHT_DIR):
        if not os.path.isfile(corpus_path(d)):
            raise SystemExit("Нет корпуса (%s). Собери PD-совет: python3 scripts/board.py seed-council" % d)
    session = {"advisors": [
        {"name": "Макиавелли", "advisor_dir": WRONG_DIR,
         "opinions": [{"marker": "blue", "quote": {"text": LINE}, "argument": "Правь так же ровно."}]},
        {"name": "Марк Аврелий", "advisor_dir": RIGHT_DIR,
         "opinions": [{"marker": "blue", "quote": {"text": LINE}, "argument": "С этого я начинаю день."}]},
    ]}
    ns, violations, _rec = m._validate_session_attribution(session)
    by_name = {a["name"]: a["opinions"][0] for a in ns["advisors"]}
    wrong, right = by_name["Макиавелли"], by_name["Марк Аврелий"]
    if wrong.get("marker") != "violation":
        raise SystemExit("Валидатор НЕ снял чужую атрибуцию — демо недостоверно.")
    if right.get("marker") != "blue":
        raise SystemExit("Валидатор снял ВЕРНУЮ атрибуцию — демо недостоверно.")
    if not violations:
        raise SystemExit("Пустой список нарушений при заведомой перепутанной цитате.")
    return wrong, right, violations[0]["reason"]


_LANG = {
    "ru": {
        "prompt": "$ consilium render-session",
        "intro": "Совет назвал ОДНУ строку. Но чьи это слова?",
        "wrong_label": "Макиавелли  [заявлено 🔵]",
        "wrong": "  ⛔ НЕ его слова: %s. Маркер снят.",
        "right_label": "Марк Аврелий  [🔵]",
        "right": "  ✅ Его. Сверено по ЕГО корпусу, слово-в-слово.",
        "cta": "Даже верную цитату в чужих устах код ловит. Автор не подменится.",
    },
    "en": {
        "prompt": "$ consilium render-session",
        "intro": "The council cited ONE line. But whose words are they?",
        "wrong_label": "Machiavelli  [claimed 🔵]",
        "wrong": "  ⛔ Not his words: %s. Marker stripped.",
        "right_label": "Marcus Aurelius  [🔵]",
        "right": "  ✅ His. Checked against HIS corpus, word-for-word.",
        "cta": "Even a true quote in the wrong mouth gets caught. No author mix-ups.",
    },
}
_REASON = {"ru": "цитата не из корпуса этого советника", "en": "not from this advisor's corpus"}


def transcript(include_prompt=True, lang="ru"):
    _wrong, _right, live_reason = run()          # валидирует до отрисовки
    s = _LANG[lang]
    reason = _REASON[lang] if lang == "en" else live_reason  # RU — живая строка валидатора
    lines = []
    if include_prompt:
        lines.append(("prompt", s["prompt"]))
    lines += [
        ("blank", ""),
        ("dim", s["intro"]),
        ("quote", "  «Of my grandfather Verus I have learned to be gentle and meek,"),
        ("quote", "   and to refrain from all anger and passion.»"),
        ("blank", ""),
        ("label", s["wrong_label"]),
        ("refuse", s["wrong"] % reason),
        ("blank", ""),
        ("label", s["right_label"]),
        ("proof", s["right"]),
        ("blank", ""),
        ("cta", s["cta"]),
    ]
    return lines


def main(argv):
    if "--check" in argv:
        wrong, right, reason = run()
        print("WRONG(Макиавелли) -> %s | %s" % (wrong["marker"], reason))
        print("RIGHT(Аврелий)    -> %s" % right["marker"])
        return 0
    lang = "en" if "--en" in argv else "ru"
    _harness.render(transcript(include_prompt="--no-prompt" not in argv, lang=lang),
                    animate="--no-anim" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
