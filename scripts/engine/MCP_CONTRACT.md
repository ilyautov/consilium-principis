MCP-совместимая форма контракта Engine (для будущего MCP-фасада / RemoteEngine).
Каждый метод = будущий MCP-инструмент с тем же именем и формой ввода/вывода.

- retrieve(question: str, advisor: str, top_k: int=3)
    → [{ text: str, score: float, source: str }]
- abstain_check(question: str, advisor: str)
    → { abstain: bool, max_score: float, threshold: float }
- fidelity_check(quote: str, advisor: str)
    → { status: "🔵"|"🟡", verbatim: bool, source: str }
- build_index(advisor: str)
    → { chunk_chars?: int }

Коллекторы (collect_pd/web/transcript) — отдельная группа build-time инструментов,
не в горячем retrieve-контуре. Добавляются в MCP-фасад при выходе «на других».
