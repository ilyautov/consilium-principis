"""Экстрактор ситуации (борроу #1 из MiroFish: seed → структура) = «захват контекста».

Сырой дамп (чат-лог конфликта, описание решения) → структура: акторы, реплики, явные вопросы.
Детерминированное ядро (парсинг) тестируем; семантику (скрытые премисы, ставки) досыпает
хост-ризонинг сверху. `frame_to_tree` — мост: позиции → дерево ситуации для движка карты.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from extractor import (
    parse_dialogue, extract_actors, collect_questions, capture_situation, frame_to_tree,
)

CHAT = """Дарья: Нам нужны ежедневные отчёты.
Это повысит прозрачность.
Андрей: Согласен, но не каждый день. Может, раз в неделю?
Илья: Это культ шлагбаума. Зачем нам это?
"""


def test_parse_dialogue_groups_multiline_by_speaker():
    turns = parse_dialogue(CHAT)
    assert len(turns) == 3
    assert turns[0]["speaker"] == "Дарья"
    assert "повысит прозрачность" in turns[0]["text"]   # вторая строка приклеена
    assert turns[1]["speaker"] == "Андрей"
    assert turns[2]["speaker"] == "Илья"


def test_parse_dialogue_ignores_timestamps_and_urls():
    # 'двоеточие' во времени/URL не должно создавать ложного спикера
    t = parse_dialogue("Илья: смотри https://x.com в 10:30 всё было ок\n")
    assert len(t) == 1
    assert t[0]["speaker"] == "Илья"
    assert "10:30" in t[0]["text"]


def test_extract_actors_unique_ordered_with_counts():
    actors = extract_actors(parse_dialogue(CHAT + "Дарья: Ещё раз про отчёты.\n"))
    names = [a["name"] for a in actors]
    assert names == ["Дарья", "Андрей", "Илья"]        # порядок появления, без дублей
    assert actors[0]["turns"] == 2                     # Дарья дважды


def test_collect_questions_finds_explicit_asks():
    qs = collect_questions(CHAT)
    assert any("раз в неделю" in q for q in qs)
    assert any("Зачем нам это" in q for q in qs)
    assert all(q.endswith("?") for q in qs)


def test_capture_situation_bundles_structure():
    cap = capture_situation(CHAT)
    assert cap["n_turns"] == 3
    assert [a["name"] for a in cap["actors"]] == ["Дарья", "Андрей", "Илья"]
    assert len(cap["questions"]) >= 2
    assert cap["turns"][0]["speaker"] == "Дарья"


def test_capture_plain_text_without_speakers():
    cap = capture_situation("Стоит ли мне уходить из спора о ежедневных отчётах?")
    assert cap["n_turns"] == 0                          # нет реплик-спикеров
    assert cap["actors"] == []
    assert len(cap["questions"]) == 1                   # вопрос всё равно поймали


def test_frame_to_tree_builds_engine_ready_tree():
    positions = [
        {"claim": "выйти из спора", "grounded": True, "strength": 0.7,
         "counters": [{"claim": "выглядишь слабым", "grounded": True, "strength": 0.2}]},  # нетто 0.5
        {"claim": "продавить своё", "grounded": True, "strength": 0.4},
    ]
    tree = frame_to_tree(positions)
    from situation import evaluate, principal_variation
    v = evaluate(tree, "competitive")
    assert v > 0
    # лучшая линия начинается с сильнейшей позиции
    assert principal_variation(tree, "competitive")[0].claim == "выйти из спора"


def test_frame_to_tree_empty_positions_is_valid_root():
    tree = frame_to_tree([])
    assert tree["move"] is None and tree["children"] == []
