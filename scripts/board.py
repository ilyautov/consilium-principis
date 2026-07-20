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
  recipes [--surface S]  — меню «что умеет совет» (S = text|widget|html; дефолт text)
  render-session <j> [--surface S] — отрисовать canon-объект заседания (S = md|widget|html)
  mcp-config [--json]    — готовый конфиг подключения как MCP-сервера (путь подставится сам)
  mcp-install [--dry-run] — подключить скриптом: мердж в claude_desktop_config.json (+бэкап)

Логика тонкая — оборачивает preflight/scaffold/ingest_telegram. Реальные вопросы юзеру
задаёт скилл разговором (см. SKILL.md «Онбординг»), сюда приходят уже структурные ответы.
Рендер: ризонинг (скилл/хост) строит canon-объект заседания, СКРИПТ детерминированно рендерит
под surface; контур/гейт 🔵 проходят до рендера. Хост сам решает, в какой surface отдать
(Cowork → widget в show_widget; голый Claude Code → md/html). См. scripts/session_render.py.
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
    with open(out, "w", encoding="utf-8") as f:        # with: не полагаемся на GC для flush/close
        f.write(scaffold_principis(answers))
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
        print(f"нет манифеста {mp} — все чанки тиром A (🟡-only; задекларируй manifest для 🔵)")
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


def cmd_mcp_config(args):
    """Готовый конфиг для подключения Consilium как MCP-сервера (путь подставляется сам).
    --json → только JSON-сниппет (для mcp.json / claude_desktop_config.json); иначе — гайд."""
    server = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    snippet = {"mcpServers": {"consilium-principis": {
        "command": sys.executable, "args": [server]}}}
    pretty = json.dumps(snippet, ensure_ascii=False, indent=2)
    if "--json" in args:
        print(pretty)
        return 0
    print("Подключение Consilium как MCP-сервера (stdio). Путь подставлен под эту машину.\n")
    print("• Claude Desktop / большинство хостов — добавь в конфиг (mcpServers):\n")
    print(pretty)
    print(f"\n• Claude Code (CLI):\n    claude mcp add consilium-principis -- {sys.executable} {server}")
    print("\n• Cowork — зарегистрируй stdio-сервер тем же command+args (точный UI см. в Cowork).")
    print("\nПосле подключения вызови тул doctor — проверит готовность машины.")
    return 0


def cmd_mcp_install(args):
    """Подключить как MCP-сервер скриптом: мердж в claude_desktop_config.json (соседей не трогает),
    с бэкапом. --dry-run — показать без записи; --config <файл> — свой путь."""
    from mcp_install import install, config_path
    cfg = None
    if "--config" in args:
        i = args.index("--config")
        cfg = args[i + 1] if i + 1 < len(args) else None
    r = install(config_file=cfg, dry_run="--dry-run" in args)
    if not r["ok"]:
        print(f"✗ {r.get('reason')}: {r.get('hint') or r.get('error')}\n  путь: {r['path']}")
        return 1
    if r.get("dry_run"):
        print(f"DRY-RUN (записи нет). Стало бы в {r['path']}:\n\n{r['preview']}")
        print("\nПрименить: убери --dry-run.")
    elif not r["changed"]:
        print(f"✓ {r['note']} — {r['path']}")
    else:
        print(f"✓ подключено → {r['path']}")
        if r.get("backup"):
            print(f"  бэкап: {r['backup']}")
        print(f"  {r['restart']}")
    return 0


def _surface(args, default):
    if "--surface" in args:
        i = args.index("--surface")
        if i + 1 < len(args):
            return args[i + 1]
    return default


def cmd_recipes(args):
    import recipes as R
    rs = R.load_recipes()
    surface = _surface(args, "text")
    if surface == "widget":
        print(R.render_widget(rs))          # для mcp__visualize__show_widget (Cowork)
    elif surface == "html":
        print(R.render_html(rs))            # самодостаточный фолбэк
    else:
        print(R.render_menu(rs))            # текст (универсально)
    return 0


def cmd_render_session(args):
    """Отрисовать canon-объект заседания (JSON-файл или '-' = stdin) под surface."""
    import session_render as SR
    src = args[0] if args and not args[0].startswith("--") else "-"
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    session = json.loads(raw)
    surface = _surface(args, "md")
    fn = {"widget": SR.render_widget, "html": SR.render_html, "md": SR.render_md}.get(surface)
    if fn is None:
        print(f"неизвестный surface: {surface} (md|widget|html)")
        return 2
    print(fn(session))
    return 0


CMDS = {"status": cmd_status, "principis": cmd_principis, "ingest-telegram": cmd_ingest_telegram,
        "validate-manifest": cmd_validate_manifest, "build-advisor": cmd_build_advisor,
        "doctor": cmd_doctor, "seed-council": cmd_seed_council, "setup-full": cmd_setup_full,
        "recipes": cmd_recipes, "render-session": cmd_render_session,
        "mcp-config": cmd_mcp_config, "mcp-install": cmd_mcp_install}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)
    sys.exit(CMDS[sys.argv[1]](sys.argv[2:]) or 0)
