"""Attended BYOK-догфуд Tier-2 федерации: реальные РАЗНЫЕ модели через НАСТОЯЩУЮ очередь.

Чем это отличается от уже сделанного:
  - `demo.py` гоняет ту же машину, но кандидаты пишет ХОСТ и метит ярлыками моделей —
    тест труб, не разнообразия.
  - `cross_model_probe.py` — standalone A/B, он ВООБЩЕ не трогает очередь/координатора/
    центральный гейт.
  - ЗДЕСЬ разные модели реально проходят координатор → очередь → исполнитель →
    централизованный гейт верности → дивергенцию → assemble. Каждая модель играет каждого
    советника СВОИМ мозгом; цитаты приводит сама, а НАШ сервер сверяет их по корпусу
    (воркер 🔵 себе не ставит — это инвариант рва).

Это первый прогон, где реальные разные модели проходят полную федеративную машину.

Рамка (docs/FEDERATION.md): personal / attended / себе-в-пользу. Сеть (OpenRouter) —
запускается РУКАМИ, не в CI. Ты сам открываешь и наблюдаешь прогон; никакой headless-
автоматизации от чужого имени.

Запуск:
    export OPENROUTER_API_KEY=...   # или лежит в .env, скрипт подхватит, не печатая
    python3 scripts/federation/dogfood_byok.py \
        --question "твой реальный вопрос" \
        --models openai/gpt-4.1,z-ai/glm-5.2 \
        --advisors machiavelli,marcus-aurelius

Прогони ≥2-3 раза на разных вопросах перед вердиктом (см. рубрику §5 в
docs/dev/federation-dogfood-checklist.md — судья это ТЫ, не скрипт).
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)

from federation.queue import SqliteBackend
from federation.coordinator import open_session, assemble
from federation.executor import claim_brief, submit_candidate
import llm_local
from mcp_server import _fidelity_check, _retrieve

# Человекочитаемые имена для промпта воркера. Ключ = slug каталога advisors/<slug>.
_DISPLAY = {
    "machiavelli": "Никколо Макиавелли",
    "marcus-aurelius": "Марк Аврелий",
    "sun-tzu": "Сунь-цзы",
}

_WORKER_PROMPT = """Ты играешь советника: {display}.
Ответь на вопрос его методом и голосом — кратко, по делу, честно (можешь и возразить).

Опору на подлинный текст {display} ты НЕ цитируешь по памяти — цитата из головы даёт 🟡
(наш сервер её не подтвердит). Вместо этого дай КОРОТКИЙ поисковый запрос НА АНГЛИЙСКОМ
(язык корпуса) — по нему сервер достанет ДОСЛОВНУЮ цитату из подлинных сочинений и сверит её
(🔵). Запрос — на английском, даже если твой ответ по-русски. Цитата не нужна — оставь пустым.

Вопрос: {question}

Верни СТРОГО JSON без пояснений и без markdown-ограды:
{{"argument": "<совет советника по-русски, 3-6 предложений>", "cite_query": "<короткий англ. запрос под твой довод, или пусто>"}}"""

_BASELINE_PROMPT = """Ответь на вопрос кратко и по делу, как один компетентный советник.
Вопрос: {question}"""


def _load_key_from_dotenv():
    """Подхватить OPENROUTER_API_KEY из .env, НЕ печатая значение. Env-переменная приоритетнее."""
    if os.getenv("OPENROUTER_API_KEY"):
        return True
    envp = os.path.join(REPO_ROOT, ".env")
    if not os.path.isfile(envp):
        return False
    with open(envp, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                return True
    return False


def _parse_candidate(raw_text):
    """Модель вернула строку → {argument, cite_query}. Терпим к markdown-ограде/мусору."""
    s = raw_text.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)   # выхватить первый JSON-объект
    if m:
        s = m.group(0)
    try:
        obj = json.loads(s)
    except Exception:
        # модель не дала валидный JSON — весь ответ идёт аргументом, без cite-запроса.
        return {"argument": raw_text.strip()[:8000], "cite_query": ""}
    return {"argument": str(obj.get("argument", "")).strip(),
            "cite_query": str(obj.get("cite_query", "")).strip()}


def _ground_via_cite(cite_query, advisor_dir, top_k=3, take=2):
    """Воркер грундится через НАШ retrieve: дословные пассажи из корпуса под англ. cite-запрос.
    Текст берём ДОСЛОВНО — центральный гейт на assemble подтвердит 🔵 (мы 🔵 сами не ставим)."""
    if not cite_query:
        return []
    try:
        r = _retrieve(cite_query, advisor_dir, top_k=top_k)
    except Exception:
        return []
    quotes, seen = [], set()
    for p in (r.get("passages") or []):
        t = (p.get("text") or "").strip()
        if not t or t in seen:
            continue                 # дедуп: retrieve иногда отдаёт near-dup пассажи
        seen.add(t)
        quotes.append({"text": t})
        if len(quotes) >= take:
            break
    return quotes


def run_worker_pass(backend, model, roles, timeout=2.0):
    """Одна модель забирает по одной реплике каждой роли и играет советника СВОИМ мозгом.
    Цитаты НЕ сочиняет — даёт англ. cite-запрос, дословный текст достаёт наш retrieve."""
    played = []
    for role in roles:
        brief = claim_brief(backend, worker_id=model, roles=[role], timeout=timeout)
        if brief.get("empty"):
            continue
        display = _DISPLAY.get(brief["role"], brief["role"])
        prompt = _WORKER_PROMPT.format(display=display, question=brief["question"])
        print("  [%s] играет роль '%s'…" % (model, brief["role"]))
        answer = llm_local.generate(prompt, model=model, temperature=0.5, timeout=120)
        parsed = _parse_candidate(answer)
        quotes = _ground_via_cite(parsed["cite_query"], brief["advisor_dir"])
        cand = {"argument": parsed["argument"], "quotes": quotes}
        res = submit_candidate(backend, brief["task_id"], model,
                               brief["claim_token"], model, cand)
        print("    cite_query=%r → достал %d пассаж(ей)" % (parsed["cite_query"], len(quotes)))
        played.append({"role": brief["role"], "model": model,
                       "n_quotes": len(quotes), "submit": res})
        if res.get("rejected"):
            print("    ⚠ отклонён: %s" % res["rejected"])
    return played


def render(envelope, question, baseline_model, baseline_text):
    L = []
    L.append("# Догфуд федерации (BYOK, реальные модели через настоящую очередь)\n")
    L.append("**Вопрос:** %s\n" % question)
    L.append("**diversity:** `%s`  ·  complete: %s\n" % (envelope["diversity"], envelope["complete"]))
    for role in envelope["roles"]:
        L.append("\n---\n\n## Роль: %s  (`%s`)" % (role["role"], role.get("advisor_dir", "")))
        if role.get("degraded"):
            L.append("\n⚠ **degraded → host_single_brain** (никто не сыграл) — diversity: reduced\n")
            continue
        div = role.get("divergence", {})
        L.append("\n**worker_models:** %s" % ", ".join(role.get("worker_models", [])))
        L.append("**дивергенция:** score=%.3f · level=%s · flagged=%s" % (
            div.get("score", 0.0), div.get("level", "?"), div.get("flagged", False)))
        L.append("**verdict:** %s · заземлённых реплик (есть 🔵): %d/%d\n" % (
            role.get("verdict", "?"), role.get("grounded_replicas", 0), len(role.get("replicas", []))))
        for i, rep in enumerate(role.get("replicas", []), 1):
            L.append("\n**реплика %d — модель `%s`:**" % (i, rep.get("worker_model", "?")))
            L.append("> %s" % rep.get("argument", "").replace("\n", "\n> "))
            if rep.get("quotes"):
                for q in rep["quotes"]:
                    src = (" — %s" % q["source"]) if q.get("source") else ""
                    L.append("  - %s «%s»%s" % (q.get("status", "🟡"), q.get("text", ""), src))
            else:
                L.append("  _(цитат не приводил)_")
    L.append("\n---\n\n## Baseline (одна модель `%s`, без совета)\n" % baseline_model)
    L.append("> %s\n" % baseline_text.strip().replace("\n", "\n> "))
    L.append("\n---\n\n## Рубрика §5 — судишь ТЫ (docs/dev/federation-dogfood-checklist.md)\n")
    L.append("- [ ] Модели дали РАЗНЫЕ ответы, или пересказали друг друга?")
    L.append("- [ ] Расхождение СОДЕРЖАТЕЛЬНОЕ (поймали разные риски), или шум формулировок?")
    L.append("- [ ] Поймала ли хоть одна модель то, что пропустили ОСТАЛЬНЫЕ **и** baseline выше?")
    L.append("- [ ] `divergence.flagged` совпал с твоим «модели реально спорили»?")
    L.append("- [ ] Заземление (🔵) распределено между моделями, или только одна оперлась на корпус?")
    L.append("\n_Прогони ≥2-3 раза на разных вопросах перед вердиктом — один прогон может быть шумом._")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="BYOK-догфуд Tier-2 федерации")
    ap.add_argument("--question", required=True, help="реальный вопрос совету (не синтетика)")
    ap.add_argument("--models", default="openai/gpt-4.1,z-ai/glm-5.2",
                    help="через запятую — РЕАЛЬНО разные модели (OpenRouter id)")
    ap.add_argument("--advisors", default="machiavelli,marcus-aurelius",
                    help="через запятую — slug каталогов advisors/<slug> с собранным корпусом")
    ap.add_argument("--baseline-model", default=None,
                    help="модель для baseline «спросить одного» (дефолт — первая из --models)")
    ap.add_argument("--session-id", default="dogfood")
    ap.add_argument("--db", default=os.path.join(REPO_ROOT, ".consilium", "federation.sqlite3"))
    args = ap.parse_args(argv)

    if not _load_key_from_dotenv():
        print("НЕТ OPENROUTER_API_KEY (ни в env, ни в .env). Экспортируй ключ и повтори.",
              file=sys.stderr)
        return 2
    os.environ["LLM_BACKEND"] = "openrouter"

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    advisors = [a.strip() for a in args.advisors.split(",") if a.strip()]
    baseline_model = args.baseline_model or models[0]

    # Предусловие: у каждого советника есть собранный корпус (иначе гейт не с чем сверять).
    for slug in advisors:
        adv_dir = os.path.join("advisors", slug)
        fc = _fidelity_check("проверка доступности корпуса", adv_dir)
        if fc.get("status") == "🚫" or "no_corpus" in str(fc):
            print("⚠ у советника '%s' не найден корпус — собери его перед догфудом." % slug,
                  file=sys.stderr)

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    backend = SqliteBackend(args.db)

    # План: каждая роль получает по реплике на каждую модель → внутри роли реплики от РАЗНЫХ моделей.
    plan = [{"role": slug, "advisor_dir": os.path.join("advisors", slug),
             "question": args.question, "replicas": len(models)} for slug in advisors]
    session = open_session(backend, args.session_id, plan)
    print("Координатор: очередь на %d роль-таск(ов) — %s" % (session["enqueued"], session["roles"]))

    for model in models:
        print("Воркер-проход: модель %s" % model)
        run_worker_pass(backend, model, advisors)

    print("Baseline: спрашиваю одну модель %s…" % baseline_model)
    baseline_text = llm_local.generate(_BASELINE_PROMPT.format(question=args.question),
                                       model=baseline_model, temperature=0.5, timeout=120)

    envelope = assemble(backend, args.session_id, _fidelity_check)
    print("\n" + render(envelope, args.question, baseline_model, baseline_text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
