"""AI-disclosure + per-persona provenance-плашка на занавесе (EU AI Act Art. 50; музейный
Lister-GPT паттерн «открытое отрицание буквальной идентичности»).

Art. 50(1)/(5): при ПЕРВОМ взаимодействии ясно и различимо сообщить, что это AI. Опенинг совета
И ЕСТЬ первое взаимодействие → плашка на занавесе закрывает требование «не позднее первого контакта».
Дисклеймер = прозрачность, НЕ правовой щит (NO FAKES): формулировка «представления, заземлённые на
текстах — не сами люди», без обещания подлинности.

Плашка несёт (внутренняя юр-записка, §Прозрачность): что это (AI-представление), метод (заземлено
на публичных текстах), что гарантирует 🔵 и чего НЕ гарантирует (не сам человек / 🟡 не его слова).
Per-persona provenance (источник/издание) — опционально под именем советника.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import session_render as sr


def _opening(**over):
    o = {"advisors": [{"name": "Марк Аврелий", "domain": "стоик", "grounded": True}],
         "invitation": "О чём совет?"}
    o.update(over)
    return o


def test_opening_carries_ai_disclosure():
    html = sr.render_opening(_opening())
    low = html.lower()
    # «это AI» + отрицание буквальной идентичности («не сами люди» / «не сам человек»).
    assert "ai" in low or "ии" in low, "нет пометки, что это AI"
    assert ("не сам" in low), "нет отрицания буквальной идентичности (Art.50/NO FAKES): не сами люди"


def test_opening_disclosure_states_grounding_and_marker_meaning():
    html = sr.render_opening(_opening())
    # метод (заземлено на текстах) + что значит 🔵 (дословно) — что гарантируется/что нет.
    assert "текст" in html.lower(), "плашка не называет метод (заземление на тексты)"
    assert "🔵" in html, "плашка не поясняет, что гарантирует маркер верности"


def test_opening_renders_per_persona_provenance_when_present():
    html = sr.render_opening(_opening(
        advisors=[{"name": "Марк Аврелий", "domain": "стоик", "grounded": True,
                   "provenance": "«Размышления», пер. Long 1862 (Gutenberg)"}]))
    assert "Long 1862" in html, "per-persona provenance (издание) не отрисован"


def test_opening_without_provenance_stays_clean():
    # Нет provenance — плашка всё равно есть, но без источника-строки у советника.
    html = sr.render_opening(_opening())
    assert "Gutenberg" not in html


def test_disclosure_present_even_with_minimal_object():
    html = sr.render_opening({"advisors": [{"name": "Сунь-Цзы"}]})
    assert "не сам" in html.lower(), "минимальный опенинг без дисклеймера — нарушает Art.50"
