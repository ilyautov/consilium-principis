"""Петля исхода U1: сёрфейсер висящих (#2) + поток записи-решения (#3).

#2 — без нуджа исходы остаются ⏳ навсегда, петля не накапливается: вытаскиваем незакрытые.
#3 — связываем куски, что лежали рядом: прогноз (premortem) при записи решения → позже сверка
с фактом → точность прогнозов; целостность леджера — hash-chain (governance). Ядро чистое.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from outcome_loop import (
    pending_from_journal, record_decision, resolve_decision, pending, loop_status, seal,
)

JOURNAL = """
### Форум-конфликт
- **ИСХОД: ⏳ pending**
### Ценообразование
- **ИСХОД: ✅** — сработало
### Партнёрство
- **ИСХОД: ⏳ pending**
"""


def test_pending_surfacer_lists_open_decisions():
    p = pending_from_journal(JOURNAL)
    assert "Форум-конфликт" in p and "Партнёрство" in p
    assert "Ценообразование" not in p           # закрыт ✅
    assert len(p) == 2


def test_record_and_resolve_decision():
    led = []
    record_decision(led, "d1", "выйти из спора", rationale="не моя игра", predicted=0.6)
    assert pending(led) == [led[0]]             # ещё не закрыт
    resolve_decision(led, "d1", actual=-0.4, endorsed=False)
    assert pending(led) == []
    assert led[0]["actual"] == -0.4 and led[0]["endorsed"] is False


def test_loop_status_tracks_prediction_accuracy_and_endorsement():
    led = []
    record_decision(led, "d1", "A", rationale="r", predicted=0.6)
    record_decision(led, "d2", "B", rationale="r", predicted=0.5)
    record_decision(led, "d3", "C", rationale="r", predicted=0.5)  # останется pending
    resolve_decision(led, "d1", actual=0.8, endorsed=True)         # знак совпал, одобрено
    resolve_decision(led, "d2", actual=-0.2, endorsed=False)       # знак разошёлся
    st = loop_status(led)
    assert st["total"] == 3 and st["resolved"] == 2 and st["pending"] == 1
    assert st["prediction_accuracy"]["directional"] == 0.5        # 1 из 2 по направлению
    assert st["endorse_rate"] == 0.5                              # 1 одобрен из 2


def test_seal_is_tamper_evident():
    led = []
    record_decision(led, "d1", "решение", rationale="r", predicted=0.3)
    chain = seal(led)
    from governance import verify_chain
    ok, broken = verify_chain(chain)
    assert ok is True
    chain[0]["record"]["rationale"] = "переписал задним числом"
    ok2, broken2 = verify_chain(chain)
    assert ok2 is False and broken2 == 0          # подмена решения ловится


def test_loop_status_empty():
    st = loop_status([])
    assert st["total"] == 0 and st["endorse_rate"] is None


# ── §4.3 замыкание петли (минимум): сёрфейсер читает СУЩЕСТВУЮЩИЕ журналы сам ──

def test_pending_from_files_scans_existing_stores(tmp_path):
    # стор НЕ новый: principis.md в корне + advisors/*/relationship.md (формат parse_decision_log)
    (tmp_path / "principis.md").write_text(
        "## Журнал решений\n### Форум\n- **ИСХОД: ⏳ pending**\n### Цены\n- **ИСХОД: ✅**\n",
        encoding="utf-8")
    adv = tmp_path / "advisors" / "marcus"
    adv.mkdir(parents=True)
    (adv / "relationship.md").write_text("### Совет о найме\nИСХОД: ⏳\n", encoding="utf-8")
    from outcome_loop import pending_from_files
    pend = pending_from_files(str(tmp_path))
    assert {p["title"] for p in pend} == {"Форум", "Совет о найме"}   # ✅ закрыт — не висит
    assert {p["source"] for p in pend} == {"principis.md", "advisors/marcus/relationship.md"}


def test_pending_from_files_missing_or_empty_is_quiet(tmp_path):
    # fail-closed: нет журналов вообще → пусто, без исключений (не ломаем холодный старт)
    from outcome_loop import pending_from_files
    assert pending_from_files(str(tmp_path)) == []
    assert pending_from_files(str(tmp_path / "нет-такого-корня")) == []


# ── Ф4: прогноз в записи журнала → поле predicted у pending-item ─────────────

def test_predicted_from_block_parses_forecast_line():
    from outcome_loop import predicted_from_block
    blk = ("2026-07-02 · шипнуть или ждать\n"
           "- Решение: шипнуть\n"
           "- Прогноз: 📐 лучший вариант — «Шипнуть»: P(лучший) 0.83, ожидание 27.4 (часы) "
           "(карта: decisions/2026-07-02-ship.json)\n"
           "- **ИСХОД: ⏳ pending**\n")
    p = predicted_from_block(blk)
    assert p.startswith("лучший вариант — «Шипнуть»")
    assert "decisions/2026-07-02-ship.json" in p


def test_predicted_from_block_fail_closed():
    from outcome_loop import predicted_from_block
    assert predicted_from_block("### X\n- **ИСХОД: ⏳**\n") is None      # строки нет
    assert predicted_from_block("- Прогноз: без глифа\n") is None       # нет 📐 — не наш формат
    assert predicted_from_block("- Прогноз: 📐   \n") is None           # пустой хвост
    assert predicted_from_block("") is None
    assert predicted_from_block(None) is None
    # 📐 в свободном тексте решения (не строка Прогноз) — не подхватывается
    assert predicted_from_block("- Решение: купить 📐 линейку\n") is None


def test_pending_entries_carry_predicted_only_when_present():
    from outcome_loop import pending_entries
    text = ("### С прогнозом\n- Прогноз: 📐 P(лучший) 0.7 (карта: decisions/a.json)\n"
            "- **ИСХОД: ⏳ pending**\n"
            "### Без прогноза\n- **ИСХОД: ⏳ pending**\n"
            "### Закрыто\n- Прогноз: 📐 x\n- **ИСХОД: ✅**\n")
    ent = pending_entries(text)
    assert [e["title"] for e in ent] == ["С прогнозом", "Без прогноза"]
    assert ent[0]["predicted"].startswith("P(лучший) 0.7")
    assert "predicted" not in ent[1]                   # fail-closed: нет строки → нет поля


def test_pending_from_files_carries_predicted(tmp_path):
    from outcome_loop import pending_from_files
    (tmp_path / "principis.md").write_text(
        "## Журнал решений\n### Шипнуть\n"
        "- Прогноз: 📐 P(лучший) 0.83 (карта: decisions/x.json)\n"
        "- **ИСХОД: ⏳ pending**\n### Ждать\n- **ИСХОД: ⏳ pending**\n",
        encoding="utf-8")
    pend = pending_from_files(str(tmp_path))
    by_title = {p["title"]: p for p in pend}
    assert by_title["Шипнуть"]["predicted"].startswith("P(лучший) 0.83")
    assert by_title["Шипнуть"]["source"] == "principis.md"
    assert "predicted" not in by_title["Ждать"]
