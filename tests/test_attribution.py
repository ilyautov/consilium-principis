"""§1.1 moat-v2: рендер-валидация МЕЖСОВЕТНИЧЕСКОЙ атрибуции.

Дыра: ров верифицирует цитату против корпуса ОДНОГО советника; сессию собирает хост и
может вставить 🔵-цитату Марка в блок мнения Макиавелли — цитата дословная, маркер честный,
автор перепутан. Фикс: на render_session каждая grounded-цитата (blue/green) обязана
верифицироваться корпусом СВОЕГО советника, иначе маркер понижается до violation с явной
причиной. Детерминированно, без LLM, fail-closed (нерезолвящийся советник → тоже понижение).
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pytest
from mcp_server import dispatch

QUOTE_A = "The universe is change; our life is what our thoughts make it."
QUOTE_B = "Men judge generally more by the eye than by the hand."


def _mk_advisor(root, slug, text, persona=None):
    d = os.path.join(root, "advisors", slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"text": text, "tier": "P1", "source": f"{slug}-src"},
                           ensure_ascii=False) + "\n")
    if persona:
        with open(os.path.join(d, "persona.md"), "w", encoding="utf-8") as f:
            f.write(persona)
    return d


@pytest.fixture()
def board(tmp_path, monkeypatch):
    """Изолированная доска: два советника с РАЗНЫМИ корпусами + alias в persona.md."""
    import mcp_server
    _mk_advisor(str(tmp_path), "aurelius", QUOTE_A,
                persona="---\nname: Марк Аврелий\naliases: [Марк Аврелий, Marcus, Marcus Aurelius]\n---\n")
    _mk_advisor(str(tmp_path), "machiavelli-b", QUOTE_B)
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    return str(tmp_path)


def _session(advisor_name, quote_text, marker="blue"):
    return {"question": "q", "synthesis": "s",
            "advisors": [{"name": advisor_name,
                          "opinions": [{"marker": marker, "argument": "довод",
                                        "quote": {"text": quote_text, "source": "src"}}]}]}


def test_own_quote_keeps_marker(board):
    # цитата советника A под советником A → маркер сохранён, нарушений нет
    r = dispatch("render_session", {"session": _session("aurelius", QUOTE_A), "surface": "md"})
    assert "attribution_violations" not in r
    assert "⛔" not in r["content"]
    assert "🔵 довод" in r["content"]                 # blue-глиф на самой строке мнения


def test_foreign_quote_demoted_to_violation(board):
    # verified-цитата советника A в opinion советника B → violation + явная причина
    r = dispatch("render_session", {"session": _session("machiavelli-b", QUOTE_A), "surface": "md"})
    v = r["attribution_violations"]
    assert len(v) == 1 and v[0]["advisor"] == "machiavelli-b"
    assert v[0]["reason"] == "цитата не из корпуса этого советника"
    assert "⛔" in r["content"] and "цитата не из корпуса этого советника" in r["content"]
    assert "🔵 довод" not in r["content"]             # grounded-маркер понижен, не сохранён
    assert "⛔ довод" in r["content"]                  # мнение рендерится глифом нарушения


def test_unresolvable_advisor_fails_closed(board):
    # имя не резолвится ни в slug, ни в persona-алиас → fail-closed понижение
    r = dispatch("render_session", {"session": _session("Неизвестный Мудрец", QUOTE_A),
                                    "surface": "md"})
    v = r["attribution_violations"]
    assert len(v) == 1 and v[0]["reason"] == "советник не резолвится"
    assert "⛔" in r["content"]


def test_persona_alias_resolves_display_name(board):
    # хост кладёт display-имя «Марк Аврелий» — резолв через persona.md name/aliases
    r = dispatch("render_session", {"session": _session("Марк Аврелий", QUOTE_A), "surface": "md"})
    assert "attribution_violations" not in r
    assert "🔵" in r["content"]


def test_explicit_advisor_dir_wins_over_name(board):
    # советник несёт явный advisor_dir → резолв имени не нужен (точный канал)
    s = _session("Кто Угодно", QUOTE_A)
    s["advisors"][0]["advisor_dir"] = "advisors/aurelius"
    r = dispatch("render_session", {"session": s, "surface": "md"})
    assert "attribution_violations" not in r


def test_yellow_and_quoteless_opinions_untouched(board):
    # 🟡-экстраполяция и мнение без цитаты — вне юрисдикции атрибуции (не grounded-заявка)
    s = {"question": "q", "synthesis": "s",
         "advisors": [{"name": "aurelius",
                       "opinions": [{"marker": "yellow", "argument": "мысль в духе",
                                     "quote": {"text": "чего нет в корпусе вообще", "source": None}},
                                    {"marker": "blue", "argument": "довод без цитаты"}]}]}
    r = dispatch("render_session", {"session": s, "surface": "md"})
    assert "attribution_violations" not in r and "⛔" not in r["content"]


def test_widget_surface_also_validated(board):
    # валидация — на входе render_session, не per-surface: widget тоже показывает нарушение
    r = dispatch("render_session", {"session": _session("machiavelli-b", QUOTE_A),
                                    "surface": "widget"})
    assert r["attribution_violations"][0]["reason"] == "цитата не из корпуса этого советника"
    assert "нарушение" in r["content"]                # пилюля violation в виджете


def test_input_session_object_not_mutated(board):
    # хост может пере-рендерить тот же объект под другой surface — вход не портим
    s = _session("machiavelli-b", QUOTE_A)
    dispatch("render_session", {"session": s, "surface": "md"})
    assert s["advisors"][0]["opinions"][0]["marker"] == "blue"
