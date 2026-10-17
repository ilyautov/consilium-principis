"""Общая кухня исполнителя федерации: промпт роли, разбор ответа модели, заземление цитат.

Раньше жила в dogfood_byok.py (research-скрипт, не шипается со скиллом). Вынесена, чтобы
рантайм-воркер на подписках (sub_worker.py) и BYOK-догфуд играли роль ОДИНАКОВО: одна и та же
форма ответа и один и тот же путь цитат → дивергенция между моделями меряет модели, а не промпты.

Инвариант рва: модель цитаты НЕ сочиняет — даёт англ. cite-запрос, дословный текст достаёт НАШ
retrieve из корпуса советника, а 🔵 ставит центральный гейт на assemble (воркер себе 🔵 не ставит).
"""
import json
import os
import re

# Человекочитаемые имена для промпта воркера. Ключ = slug каталога advisors/<slug>.
DISPLAY = {
    "machiavelli": "Никколо Макиавелли",
    "marcus-aurelius": "Марк Аврелий",
    "sun-tzu": "Сунь-цзы",
    "epictetus": "Эпиктет",
}

WORKER_PROMPT = """Ты играешь советника: {display}.
Ответь на вопрос его методом и голосом — кратко, по делу, честно (можешь и возразить).
Опору на подлинный текст {display} ты НЕ цитируешь по памяти — цитата из головы даёт 🟡
(наш сервер её не подтвердит). Вместо этого дай КОРОТКИЙ поисковый запрос НА АНГЛИЙСКОМ
(язык корпуса) — по нему сервер достанет ДОСЛОВНУЮ цитату из подлинных сочинений и сверит её
(🔵). Запрос — на английском, даже если твой ответ по-русски. Пиши его как фразу, которую мог бы
написать сам автор (образ, мысль, ключевые слова довода), БЕЗ имени автора и названий книг —
по ним находятся предисловия и библиография, а не его текст. Цитата не нужна — оставь пустым.

Вопрос: {question}

Верни СТРОГО JSON без пояснений и без markdown-ограды:
{{"argument": "<совет советника по-русски, 3-6 предложений>", "cite_query": "<короткий англ. запрос под твой довод, или пусто>"}}"""

_NAME_LINE = re.compile(r"^\s*(?:name|имя)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def display_name(role, advisor_dir=None):
    """Имя советника для промпта: словарь известных → name:/первый заголовок persona.md → slug.
    Ошибки чтения не роняют воркера (имя — косметика, верность держит сервер)."""
    if role in DISPLAY:
        return DISPLAY[role]
    if advisor_dir:
        try:
            with open(os.path.join(advisor_dir, "persona.md"), encoding="utf-8") as fh:
                head = fh.read(4000)
            m = _NAME_LINE.search(head) or _HEADING.search(head)
            if m:
                return m.group(1).strip().strip('"').strip("'")[:120]
        except OSError:
            pass
    return role


def parse_candidate(raw_text):
    """Модель вернула строку → {argument, cite_query}. Терпим к markdown-ограде/мусору."""
    s = (raw_text or "").strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)   # выхватить первый JSON-объект
    if m:
        s = m.group(0)
    try:
        obj = json.loads(s)
    except Exception:
        # модель не дала валидный JSON — весь ответ идёт аргументом, без cite-запроса.
        return {"argument": (raw_text or "").strip()[:8000], "cite_query": ""}
    if not isinstance(obj, dict):
        return {"argument": (raw_text or "").strip()[:8000], "cite_query": ""}
    return {"argument": str(obj.get("argument", "")).strip(),
            "cite_query": str(obj.get("cite_query", "")).strip()}


def ground_via_cite(cite_query, advisor_dir, retrieve_fn, top_k=3, take=2, errors=None):
    """Воркер грундится через НАШ retrieve: дословные пассажи из корпуса под англ. cite-запрос.
    Текст берём ДОСЛОВНО — центральный гейт на assemble подтвердит 🔵 (мы 🔵 сами не ставим).
    errors (опц. список): сюда пишется причина, если retrieve отказал/упал — иначе «0 цитат»
    неотличимо от «модель не просила цитату» (живой догфуд 2026-10-13: советник вне advisors/
    чекаута → retrieve вернул {"error"}, воркер молча сдал реплики без опоры)."""
    if not cite_query:
        return []
    try:
        r = retrieve_fn(cite_query, advisor_dir, top_k=top_k)
    except Exception as e:
        if errors is not None:
            errors.append("retrieve упал: %s" % type(e).__name__)
        return []
    if isinstance(r, dict) and r.get("error"):
        if errors is not None:
            errors.append("retrieve отказал: %s" % str(r["error"])[:200])
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
