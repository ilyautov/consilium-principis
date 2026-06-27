#!/usr/bin/env python3
"""Экстрактор ситуации (борроу #1 из MiroFish) = «захват контекста» для ситуационной карты.

Сырой дамп (чат-лог конфликта, описание решения) → структура: акторы, реплики, явные вопросы.
Это ДЕТЕРМИНИРОВАННЫЙ захват — семантику (скрытые премисы, ставки, телос) досыпает хост-ризонинг
поверх. `frame_to_tree` — мост: позиции (которые наполнил ризонинг) → дерево движка `situation`.

Парсинг диалога — эвристика: строка «Имя: реплика» (двоеточие+пробел, имя ≤4 слов, с буквой,
без `://`) открывает реплику; строки без этого приклеиваются к текущему спикеру. Так время
`10:30` и `https://` не создают ложных спикеров.
"""
import re
from situation import Move, node

_TIMESTAMP = re.compile(r"^\[[^\]]*\]\s*")                   # ведущий [25.06.2026 22:04]
_SPEAKER = re.compile(r"^(?P<spk>[^:\n]{1,60}):\s+(?P<txt>.+)$")


def _clean_speaker(spk):
    """'Дарья Балковская | Бизнес-трекер' → 'Дарья Балковская' (отбросить роль после '|')."""
    return spk.split("|")[0].strip()


def _looks_like_speaker(name):
    return bool(re.search(r"[^\W\d_]", name)) and len(name.split()) <= 5 and "://" not in name


def parse_dialogue(text):
    """Текст → [{speaker, text}]. Берёт и 'Имя: текст', и '[таймстамп] Имя | роль: текст'
    (формат логов мессенджеров). Время 10:30 и https:// ложных спикеров не дают."""
    turns = []
    for line in text.splitlines():
        s = _TIMESTAMP.sub("", line.strip())                # снять ведущий [таймстамп]
        m = _SPEAKER.match(s)
        if m:
            name = _clean_speaker(m.group("spk"))
            if _looks_like_speaker(name):
                turns.append({"speaker": name, "text": m.group("txt").strip()})
                continue
        if turns and line.strip():
            turns[-1]["text"] += "\n" + line.strip()        # продолжение текущей реплики
    return turns


def extract_actors(turns):
    """Уникальные спикеры в порядке появления + число реплик."""
    order, counts = [], {}
    for t in turns:
        s = t["speaker"]
        if s not in counts:
            order.append(s)
        counts[s] = counts.get(s, 0) + 1
    return [{"name": s, "turns": counts[s]} for s in order]


def collect_questions(text):
    """Явные вопросы — фрагменты, заканчивающиеся на «?»."""
    out = []
    for frag in re.findall(r"[^.!?\n]*\?", text):
        q = frag.strip()
        if q and q not in out:
            out.append(q)
    return out


def capture_situation(text):
    """Структурный захват ситуации: акторы + реплики + вопросы (вход для карты и рейм-чека)."""
    turns = parse_dialogue(text)
    return {
        "actors": extract_actors(turns),
        "turns": turns,
        "questions": collect_questions(text),
        "n_turns": len(turns),
    }


def frame_to_tree(positions):
    """Позиции → дерево ситуации для движка. Каждая позиция = твой ход + её контрмеры.
    positions: [{claim, grounded, strength, counters:[{claim, grounded, strength}]}]."""
    children = []
    for p in positions:
        you = Move("you", p["claim"], grounded=p.get("grounded", False),
                   strength=p.get("strength", 0.0))
        counters = [node(Move("opponent", c["claim"], grounded=c.get("grounded", False),
                              strength=c.get("strength", 0.0)))
                    for c in p.get("counters", [])]
        children.append(node(you, counters))
    return node(None, children)
