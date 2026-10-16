#!/usr/bin/env python3
"""Исполнитель федерации на ПОДПИСКАХ: Claude Code / Codex / Kimi Code CLI играют советников.

Раньше исполнителем была отдельная ИНТЕРАКТИВНАЯ сессия клиента (путь A в docs/FEDERATION.md) —
юзер руками открывал Codex и говорил «забери роль». Здесь то же самое без ручной беготни: для
каждого выбранного CLI поднимается поток-воркер, он по очереди забирает по ОДНОЙ реплике каждой
роли, играет советника своей моделью через cli_backends.generate и сдаёт СЫРОГО кандидата.
Маркеры 🔵 ставит наш сервер на assemble (инвариант рва не меняется).

Почему «по одной реплике роли на бэкенд»: если один быстрый CLI заберёт все реплики роли,
разнообразие схлопнется в одну модель. claim(roles=[role]) по разу на роль → каждая модель
высказывается по каждому советнику; невзятые реплики честно деградируют в host_single_brain.

Рамка: personal / attended. Запускает сам юзер (или хост с его ЯВНОГО согласия, Rule 0) на своей
машине под своими логинами CLI; вопрос уходит провайдерам подписок — это пишется в отчёт.

Запуск:
    # открыть сессию и сыграть её всеми установленными подписками, собрать результат
    python3 scripts/federation/sub_worker.py --open --session s1 \\
        --question "Брать ли кредит под расширение?" \\
        --advisors advisors/marcus-aurelius,advisors/machiavelli --backends claude,codex
    # только доиграть уже открытую хостом сессию (federation_open) и выйти
    python3 scripts/federation/sub_worker.py --session s1 --backends claude,codex,kimi
"""
import argparse
import json
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS_DIR)

import cli_backends                                                  # noqa: E402
from federation.executor import claim_brief, submit_candidate, heartbeat_task  # noqa: E402
from federation.worker_common import (WORKER_PROMPT, display_name,  # noqa: E402
                                      parse_candidate, ground_via_cite)

CLAIM_TIMEOUT = 0.5


def worker_id_for(backend, model=None):
    """Стабильный worker_id/worker_model: «claude», «codex:gpt-5» — видно в assemble, чья реплика."""
    return backend + (":" + model if model else "")


def play_roles(queue, backend, roles, generate_fn, retrieve_fn, model=None, log=print,
               timeout=cli_backends.DEFAULT_TIMEOUT):
    """Один бэкенд проходит роли по разу. → список {role, ok, n_quotes | error}.
    Сбой CLI (квота/логин/таймаут) на первой же роли → бэкенд выбывает целиком: остальные роли
    он тоже не сыграет (квота не воскреснет через минуту), а взятая реплика возвращается nack'ом."""
    wid = worker_id_for(backend, model)
    played = []
    for role in roles:
        brief = claim_brief(queue, worker_id=wid, roles=[role], timeout=CLAIM_TIMEOUT)
        if brief.get("empty"):
            continue
        prompt = WORKER_PROMPT.format(display=display_name(brief["role"], brief["advisor_dir"]),
                                      question=brief["question"])
        log("  [%s] играет «%s»…" % (wid, brief["role"]))
        try:
            answer = generate_fn(prompt, backend, model=model, timeout=timeout)
        except cli_backends.CLIBackendError as e:
            # nack сразу возвращает реплику в pending: её доиграет другой бэкенд/хост, а не ждём
            # 300 с lease. Реплика, исчерпавшая попытки, честно хоронится очередью (dead).
            queue.nack(brief["task_id"], wid, brief["claim_token"], "%s:%s" % (backend, e.kind))
            log("  [%s] выбыл: %s" % (wid, e))
            played.append({"role": brief["role"], "ok": False, "error": e.kind, "detail": e.detail})
            return played
        heartbeat_task(queue, brief["task_id"], wid, brief["claim_token"])
        parsed = parse_candidate(answer)
        ground_errors = []
        quotes = ground_via_cite(parsed["cite_query"], brief["advisor_dir"], retrieve_fn,
                                 errors=ground_errors)
        for err in ground_errors:
            log("  [%s] ⚠ %s" % (wid, err))
        res = submit_candidate(queue, brief["task_id"], wid, brief["claim_token"], wid,
                               {"argument": parsed["argument"], "quotes": quotes})
        if res.get("rejected"):
            log("  [%s] кандидат отклонён: %s" % (wid, res["rejected"]))
            played.append({"role": brief["role"], "ok": False, "error": "rejected",
                           "detail": res["rejected"]})
        else:
            row = {"role": brief["role"], "ok": True, "n_quotes": len(quotes),
                   "cite_query": parsed["cite_query"]}
            if ground_errors:
                row["ground_errors"] = ground_errors
            played.append(row)
    return played


def run(queue, backends, roles, generate_fn=None, retrieve_fn=None, models=None, log=print,
        timeout=cli_backends.DEFAULT_TIMEOUT):
    """Все бэкенды параллельно (поток на CLI — они независимы и ждут сеть). → {backend: played}.
    Неустановленный CLI в отчёте как missing, а не тихо пропущен."""
    generate_fn = generate_fn or cli_backends.generate
    if retrieve_fn is None:
        from mcp_server import _retrieve as retrieve_fn
    models = models or {}
    report, threads = {}, []
    for b in backends:
        if b not in cli_backends.BACKENDS or not cli_backends.available(b):
            report[b] = [{"ok": False, "error": "missing", "detail": "CLI не установлен"}]
            continue

        def _go(b=b):
            report[b] = play_roles(queue, b, roles, generate_fn, retrieve_fn,
                                   model=models.get(b), log=log, timeout=timeout)
        t = threading.Thread(target=_go, name="sub-worker-" + b, daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    return report


def session_roles(queue, session_id):
    """Роли открытой сессии в порядке постановки (из строк тасков — их писал координатор)."""
    seen = []
    for row in queue.results(session_id, status=None):
        if row["role"] not in seen:
            seen.append(row["role"])
    return seen


def _parse_models(spec):
    """'claude=opus,codex=gpt-5' → {'claude': 'opus', 'codex': 'gpt-5'}."""
    out = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сыграть роли совета-федерации подписочными CLI")
    ap.add_argument("--session", required=True)
    ap.add_argument("--backends", default="", help="claude,codex,kimi (пусто = все установленные)")
    ap.add_argument("--models", default="", help="claude=opus,codex=gpt-5 (опц.)")
    ap.add_argument("--roles", default="", help="роли через запятую (пусто = все роли сессии)")
    ap.add_argument("--open", action="store_true", help="открыть сессию самому (нужны --question/--advisors)")
    ap.add_argument("--question", default="")
    ap.add_argument("--advisors", default="", help="каталоги советников через запятую")
    ap.add_argument("--no-assemble", action="store_true")
    ap.add_argument("--timeout", type=int, default=cli_backends.DEFAULT_TIMEOUT)
    a = ap.parse_args(argv)

    import mcp_server
    backends = [b.strip() for b in a.backends.split(",") if b.strip()] or cli_backends.detect()
    if not backends:
        print(json.dumps({"error": "не найден ни один подписочный CLI (claude/codex/kimi)"},
                         ensure_ascii=False))
        return 2
    roles = [r.strip() for r in a.roles.split(",") if r.strip()]
    if a.open:
        dirs = [d.strip() for d in a.advisors.split(",") if d.strip()]
        if not a.question.strip() or not dirs:
            print(json.dumps({"error": "--open требует --question и --advisors"}, ensure_ascii=False))
            return 2
        plan = [{"role": os.path.basename(os.path.normpath(d)), "advisor_dir": d,
                 "question": a.question} for d in dirs]
        opened = mcp_server._federation_open(a.session, plan, replicas_default=len(backends))
        if opened.get("error"):
            print(json.dumps(opened, ensure_ascii=False))
            return 2
        roles = roles or [p["role"] for p in plan]
    if not roles:
        roles = session_roles(mcp_server._fed_backend(), a.session)
    if not roles:
        print(json.dumps({"error": "не знаю роли сессии — передай --roles"}, ensure_ascii=False))
        return 2
    print("Подписки: %s · роли: %s · вопрос уходит провайдерам этих подписок."
          % (", ".join(backends), ", ".join(roles)), file=sys.stderr)
    report = run(mcp_server._fed_backend(), backends, roles, models=_parse_models(a.models),
                 log=lambda m: print(m, file=sys.stderr), timeout=a.timeout)
    out = {"session_id": a.session, "workers": report}
    if not a.no_assemble:
        out["assembled"] = mcp_server._federation_assemble(a.session)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
