#!/usr/bin/env python3
"""Единая точка входа сборки доски (шасси). Юзер в Claude говорит — скилл зовёт это.

  status                 — что готово + один приоритетный следующий шаг (онбординг за руку)
  principis <ans.json>   — собрать principis.md из ответов (не перезатирает без --force)
  ingest-telegram <@h>   — выкачать публичный канал в корпус-Принцепса (твои слова = P1)
  validate-manifest <d>  — проверить тир-манифест советника (маркеры реально в тексте? ров цел?)
  build-advisor <d>      — собрать советника в один шаг: манифест-гейт → corpus → kernels → индекс
  seed-council           — собрать стартовый совет PD-мудрецов с нуля (Аврелий + Эпиктет)
  doctor                 — health-check: Python, скилл установлен, тир, самотест рва
  setup-full             — поднять FULL-тир: инструкция по ollama + авто-pull модели bge-m3

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


def cmd_validate_manifest(args):
    from manifest_builder import validate_manifest
    if not args:
        print("дай advisors/{имя}")
        return 1
    adv = args[0]
    sd = os.path.join(adv, "sources")
    mp = os.path.join(sd, "manifest.json")
    if not os.path.isfile(mp):
        print(f"нет манифеста {mp} (без него всё P1 — бэк-компат)")
        return 0
    res = validate_manifest(json.load(open(mp, encoding="utf-8")), sd)
    if res["ok"]:
        print("✓ манифест валиден — тиры не съедут")
        return 0
    print(f"✗ {len(res['problems'])} проблем (ров под угрозой):")
    for p in res["problems"]:
        print("   ", p)
    return 1


def cmd_build_advisor(args):
    from build_orchestrator import build_advisor_full
    if not args:
        print("дай advisors/{имя}")
        return 1
    res = build_advisor_full(args[0], run_kernels="--no-kernels" not in args,
                             run_index="--no-index" not in args)
    if not res["ok"]:
        print(f"✗ остановлено на {res['stopped_at']}: {len(res['problems'])} проблем манифеста")
        for p in res["problems"]:
            print("   ", p)
        return 1
    for s in res["steps"]:
        print(f"  • {s['step']}: {'✓' if s['ok'] else '⚠'} {s.get('note', '') or s.get('chunks', s.get('count',''))}")
    st = res["status"]
    print(f"→ {st['name']}: {st['chunks']} чанков, {'🔵-готов' if st['blue_eligible'] else 'нет P1/P2'}, "
          f"{'+кернелы' if st['has_kernels'] else 'без кернелов'}")
    return 0


def cmd_doctor(args):
    from doctor import run_doctor
    r = run_doctor(_root())
    print(f"Consilium-Principis — health-check: {'✓ ЗДОРОВ' if r['healthy'] else '✗ ЕСТЬ ПРОБЛЕМЫ'}")
    for c in r["checks"]:
        print(f"  {'✓' if c['ok'] else '✗'} {c['name']:<16} {c['detail']}")
    return 0 if r["healthy"] else 1


def cmd_seed_council(args):
    from seed import run_seed_council, SEED_ADVISORS
    print(f"Собираю стартовый совет ({len(SEED_ADVISORS)} PD-мудрецов): "
          f"{', '.join(s['display'] for s in SEED_ADVISORS)}")
    print("Fetch → манифест → валидация-гейт → corpus → kernels. Минуты (kernels нужен ollama).")
    results = run_seed_council(_root())
    ok = 0
    for r in results:
        if r["ok"]:
            ok += 1
            st = (r.get("build") or {}).get("status", {})
            print(f"  ✓ {r['name']}: {st.get('chunks', '?')} чанков, "
                  f"{'🔵-готов' if st.get('blue_eligible') else 'нет P1'}")
        else:
            print(f"  ✗ {r['name']}: упал на {r.get('stage')} — {r.get('detail') or r.get('problems')}")
    print(f"→ Собрано {ok}/{len(results)}. Дальше: /board council: <твой вопрос>")
    return 0 if ok else 1


def cmd_setup_full(args):
    from setup_full import run_setup
    print("Настройка FULL-тира (семантик-ретрив). Системный ollama не ставлю молча — даю команду;")
    print("модель bge-m3 в стоящий ollama тяну сам.")
    out = run_setup(consent="--no-pull" not in args)
    for r in out["results"]:
        print(f"  [{r['step']}] {'✓ сделано' if r.get('ran') else '→ ' + r['detail']}")
    f = out["final"]
    ok = f["ollama_running"] and f["bge_m3_present"]
    print(f"→ FULL-тир: {'✓ доступен' if ok else '✗ ещё нет (выполни шаги выше, потом повтори)'}")
    return 0 if ok else 1


CMDS = {"status": cmd_status, "principis": cmd_principis, "ingest-telegram": cmd_ingest_telegram,
        "validate-manifest": cmd_validate_manifest, "build-advisor": cmd_build_advisor,
        "doctor": cmd_doctor, "seed-council": cmd_seed_council, "setup-full": cmd_setup_full}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)
    sys.exit(CMDS[sys.argv[1]](sys.argv[2:]) or 0)
