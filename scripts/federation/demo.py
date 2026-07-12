"""Офлайн end-to-end демо совета-федерации: ОДНА машина, хост симулирует 3 дивергентных
воркера на роль (разные worker_model-ярлыки), настоящая очередь+исполнитель (claim_brief/
submit_candidate — не короткий путь через backend напрямую), РЕАЛЬНЫЙ гейт верности
(mcp_server._fidelity_check против tmp-корпуса, не мок), и рендер в читаемый markdown.

Это догфуд-энейблмент + регрессионный тест плюмбинга (очередь → исполнитель → координатор →
гейт → рендер), НЕ доказательство кросс-модельного разнообразия: все кандидаты в этом демо
написаны хостом и ПОМЕЧЕНЫ разными моделями — сам текст аргументов не порождён отдельными
LLM. render_council_md честно проговаривает это ограничение в футере.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from federation.coordinator import open_session, assemble
from federation.executor import claim_brief, submit_candidate

WORKER_MODELS = ["claude-sonnet-5", "gemini-3-pro", "gpt-5.2"]

# Реальные (public-domain) короткие цитаты — verbatim-совпадение с корпусом → 🔵.
_REAL_QUOTES = {
    "aurelius": "Confine thyself to the present.",
    "machiavelli": "It is much safer to be feared than loved.",
}
# Сфабрикованная цитата — НЕ существует ни в одном корпусе → остаётся 🟡 (гейт дискриминирует).
_FABRICATED_QUOTE = "This precise sentence was never written by any advisor in this corpus."

# Три расходящихся архетипа аргумента на роль: действие / осторожность / контрарианство.
_ARGUMENT_TEMPLATES = {
    "aurelius": [
        "Действуй сейчас: единственное, чем ты владеешь, — это настоящее дело. Не откладывай.",
        "Прежде чем действовать, проверь: это в твоей власти изменить, или ты тревожишься о чужом?",
        "Сама постановка вопроса ошибочна — спокойствие не результат действия, а взгляд на него.",
    ],
    "machiavelli": [
        "Действуй решительно: колебание читается слабостью, а слабость приглашает удар.",
        "Не спеши — сначала выясни, на чьей стороне реальная сила, потом выбирай ход.",
        "Вопрос не в том, действовать ли, а в том, кто понесёт цену ошибки — раздели риск заранее.",
    ],
}


def _plan(advisor_dirs, question, replicas=3):
    return [
        {"role": role, "advisor_dir": adir, "question": question, "replicas": replicas}
        for role, adir in advisor_dirs.items()
    ]


def _worker_candidate(role, replica_idx):
    """Собрать кандидата хоста-как-воркера. Один кандидат на роль несёт реальную verbatim-цитату
    (🔵-кандидат), остальные — сфабрикованную (остаются 🟡): оба исхода гейта видны в envelope."""
    argument = _ARGUMENT_TEMPLATES[role][replica_idx % len(_ARGUMENT_TEMPLATES[role])]
    if replica_idx == 0:
        quote_text = _REAL_QUOTES[role]
    else:
        quote_text = _FABRICATED_QUOTE
    return {"argument": argument, "quotes": [{"text": quote_text}]}


def _play_queue(backend, worker_id_prefix="worker"):
    """Забирает ВСЕ pending-таски через claim_brief/submit_candidate (настоящий плюмбинг очереди
    и исполнителя — не короткий путь через backend напрямую). Возвращает число сыгранных тасков."""
    played = 0
    role_replica_counter = {}
    while True:
        brief = claim_brief(backend, "%s-%d" % (worker_id_prefix, played), roles=None, timeout=0.2)
        if brief.get("empty"):
            break
        role = brief["role"]
        idx = role_replica_counter.get(role, 0)
        role_replica_counter[role] = idx + 1
        worker_model = WORKER_MODELS[idx % len(WORKER_MODELS)]
        candidate = _worker_candidate(role, idx)
        submit_candidate(backend, brief["task_id"], "%s-%d" % (worker_id_prefix, played),
                          brief["claim_token"], worker_model, candidate)
        played += 1
    return played


def run_demo(backend, verify_fn, advisor_dirs, render=True, session_id="demo-session",
             question="Тяну четыре направления сразу. На чём сфокусироваться?"):
    """Проиграть полный демо-совет: open_session → claim/submit по очереди (executor) →
    assemble (координатор + реальный гейт). Возвращает envelope, либо (envelope, markdown)
    если render=True."""
    plan = _plan(advisor_dirs, question, replicas=3)
    session = open_session(backend, session_id, plan, replicas_default=3)
    _play_queue(backend)
    envelope = assemble(backend, session["session_id"], verify_fn)
    if render:
        return envelope, render_council_md(envelope)
    return envelope


_ROLE_TITLES = {
    "aurelius": "Марк Аврелий (Стоик)",
    "machiavelli": "Макиавелли",
}


def _role_title(role):
    return _ROLE_TITLES.get(role, role)


def _render_role(role_out):
    lines = []
    role = role_out["role"]
    lines.append("### %s (`%s`)" % (_role_title(role), role))
    if role_out.get("degraded"):
        lines.append("")
        lines.append("⛔ роль деградировала — ни одна реплика не завершилась. Режим: "
                      "`host_single_brain`, вердикт: **ESCALATE**.")
        lines.append("")
        return lines

    rep = role_out.get("representative")
    lines.append("")
    if rep:
        lines.append("**Представитель:** %s" % rep.get("argument", "").strip())
        lines.append("")
        for q in rep.get("quotes", []):
            src = (" — *%s*" % q["source"]) if q.get("source") else ""
            lines.append("- %s «%s»%s" % (q["status"], q["text"], src))
    else:
        lines.append("**Представитель:** нет (ни один кандидат не заземлён).")
    lines.append("")

    div = role_out["divergence"]
    flag = " ⚠ помечено" if div.get("flagged") else ""
    lines.append("**Дивергенция:** %.4f (%s%s)" % (div["score"], div["level"], flag))
    lines.append("")
    models = ", ".join(role_out["worker_models"])
    lines.append("**Модели-воркеры (%d):** %s" % (len(role_out["worker_models"]), models))
    lines.append("")
    lines.append("**Заземлённых реплик:** %d/%d" % (role_out["grounded_replicas"],
                                                      len(role_out["replicas"])))
    lines.append("")
    lines.append("**Вердикт:** %s" % role_out["verdict"])
    lines.append("")

    lines.append("<details><summary>Все %d реплики (сырые, не схлопнуты)</summary>" %
                  len(role_out["replicas"]))
    lines.append("")
    for i, cand in enumerate(role_out["replicas"], 1):
        lines.append("%d. *(%s)* %s" % (i, cand.get("worker_model", "?"), cand.get("argument", "").strip()))
        for q in cand.get("quotes", []):
            src = (" — *%s*" % q["source"]) if q.get("source") else ""
            lines.append("   - %s «%s»%s" % (q["status"], q["text"], src))
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return lines


def render_council_md(envelope):
    """Рендер envelope в читаемый markdown (русский регистр, см. docs/demo/demo-scenario.md)."""
    lines = []
    lines.append("# Демо: офлайн заседание совета-федерации")
    lines.append("")
    lines.append("Сессия `%s` — разнообразие: **%s**, статус: %s." % (
        envelope["session_id"], envelope["diversity"],
        "завершено" if envelope["complete"] else "не завершено"))
    if envelope.get("degraded_roles"):
        lines.append("")
        lines.append("⛔ Деградированные роли: %s" % ", ".join(envelope["degraded_roles"]))
    lines.append("")
    lines.append("## Роли")
    lines.append("")
    for role_out in envelope["roles"]:
        lines.extend(_render_role(role_out))

    lines.append("## Что показывает демо")
    lines.append("")
    lines.append(
        "Это плюмбинг ОДНОЙ машины: очередь (`federation/queue.py`) → исполнитель "
        "(`federation/executor.py`, реальные `claim_brief`/`submit_candidate`) → координатор "
        "(`federation/coordinator.py`) → **реальный** гейт верности (`mcp_server._fidelity_check` "
        "против настоящего корпуса, не мок) → рендер. Это НЕ доказательство кросс-модельного "
        "разнообразия: в этом демо ВСЕ кандидаты написаны хостом и лишь ПОМЕЧЕНЫ разными "
        "worker_model — сами тексты аргументов не порождены независимыми LLM. Что доказано "
        "по-настоящему: гейт дискриминирует (сфабрикованная цитата остаётся 🟡, дословная — 🔵), "
        "сырые реплики сохраняются (не схлопываются в best-of-N), дивергенция считается."
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import tempfile

    from federation.queue import SqliteBackend

    ROOT = os.path.dirname(SCRIPTS_DIR)
    sys.path.insert(0, SCRIPTS_DIR)
    from mcp_server import _fidelity_check
    from corpusbuild.paths import corpus_path

    def _make_advisor(base_dir, chunks, name):
        adv = os.path.join(base_dir, name)
        cp = corpus_path(adv)                      # резолвер, не литерал (test_reader_migration гард)
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        return adv

    with tempfile.TemporaryDirectory(prefix="federation-demo-") as tmp_dir:
        backend = SqliteBackend(os.path.join(tmp_dir, "demo.sqlite3"))
        advisor_dirs = {
            "aurelius": _make_advisor(tmp_dir, [
                {"text": "Confine thyself to the present.", "tier": "P1",
                 "source": "Meditations 7.29 (Long)"},
            ], "aurelius"),
            "machiavelli": _make_advisor(tmp_dir, [
                {"text": "It is much safer to be feared than loved.", "tier": "P1",
                 "source": "The Prince, ch. 17"},
            ], "machiavelli"),
        }
        envelope, md = run_demo(backend, _fidelity_check, advisor_dirs, render=True)

    out_path = os.path.join(ROOT, "docs", "demo", "federation-council-sample.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    print(md)
    print("\n[записано в %s]" % out_path, file=sys.stderr)
