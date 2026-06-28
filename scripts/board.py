#!/usr/bin/env python3
"""Единая точка входа сборки доски (шасси). Юзер в Claude говорит — скилл зовёт это.

  status                 — что готово + один приоритетный следующий шаг (онбординг за руку)
  principis <ans.json>   — собрать principis.md из ответов (не перезатирает без --force)
  ingest-telegram <@h>   — выкачать публичный канал в корпус-Принцепса (твои слова = P1)

Логика тонкая — оборачивает preflight/scaffold/ingest_telegram. Реальные вопросы юзеру
задаёт скилл разговором (см. SKILL.md «Онбординг»), сюда приходят уже структурные ответы.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cmd_status(args):
    from preflight import preflight, _report
    from scaffold import next_step
    pf = preflight(_root())
    print(_report(pf))
    ns = next_step(pf)
    print(f"\n→ Следующий шаг: {ns['action']} — {ns['why']}")
    return 0


def cmd_principis(args):
    from scaffold import scaffold_principis
    if not args:
        print("дай путь к answers.json (ответы юзера)")
        return 1
    answers = json.load(open(args[0], encoding="utf-8"))
    out = os.path.join(_root(), "principis.md")
    if os.path.isfile(out) and "--force" not in args:
        print("principis.md уже есть — добавь --force чтобы перезаписать (или правь руками)")
        return 1
    open(out, "w", encoding="utf-8").write(scaffold_principis(answers))
    print(f"✓ principis.md собран (подача={answers.get('interface_mode', 'rigor')}). "
          f"Вектор держим живым — совет допросит на первом заседании.")
    return 0


def cmd_ingest_telegram(args):
    from ingest_telegram import ingest
    if not args:
        print("дай @handle публичного канала")
        return 1
    res = ingest(args[0])
    print(f"[telegram] @{res['handle']}: {res['posts']} постов → {res['out']}")
    if res["posts"] == 0:
        print("0 постов — приватный/пустой канал, неверный handle, или сеть заблокирована.")
    return 0


CMDS = {"status": cmd_status, "principis": cmd_principis, "ingest-telegram": cmd_ingest_telegram}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)
    sys.exit(CMDS[sys.argv[1]](sys.argv[2:]) or 0)
