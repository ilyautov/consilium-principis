#!/usr/bin/env python3
"""§1.3 moat-v2: дешёвый детерминированный детект языкового мисматча запрос↔корпус.

Дыра UX: «запрос давай на языке корпуса» жило строчкой в note — хост забыл → тихая
деградация всего ретрив-пайплайна (кросс-язычный запрос против англ. корпуса даёт
схлопнутые скоры). Этот модуль превращает тихую деградацию в ЯВНУЮ директиву хосту:
retrieve/cite добавляют `language_mismatch: true` + «переведи запрос на язык корпуса
и повтори». БЕЗ автоперевода — перевод остаётся ризонингом хоста (валидированный лифт
translate-query, см. memory: translate query not corpus).

Механика (0 LLM, 0 сети):
  • script_of(query) — доля кириллицы vs латиницы; >20% каждого скрипта → None
    (смешанный/неоднозначный запрос НЕ флагуем — ложная тревога хуже молчания);
  • corpus_script(advisor_dir) — язык корпуса из sources/manifest.json (`lang`
    per-source, единогласно), иначе вывод по сэмплу чанков corpus.jsonl (та же
    скрипт-эвристика). Кэш на advisor_dir — вывод делается один раз;
  • mismatch(query, advisor_dir) — dict с флагом+директивой или None. Никогда не бросает.
"""
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild.paths import corpus_path

# ISO-коды языков на кириллице; всё прочее известное считаем латиницей (наши корпуса —
# en/la/it-переводы). Незнакомый код → вывод по чанкам (fail-safe: лучше сэмпл, чем догадка).
CYRILLIC_LANGS = {"ru", "uk", "bg", "be", "sr", "mk", "kk", "ky", "tg", "mn"}
LATIN_LANGS = {"en", "la", "it", "fr", "de", "es", "pt", "nl", "pl", "cs", "sv", "no", "da", "fi"}

MIN_LETTERS = 3          # меньше — не о чем судить (пустой/символьный запрос)
DOMINANCE = 0.80         # скрипт «определён», если его доля > 80% (иначе смешанный → None)
SAMPLE_CHUNKS = 50       # сэмпл корпуса для вывода языка без манифеста

_CORPUS_CACHE = {}       # advisor_dir(abs) → (script|None, lang_label|None)


def script_of(text):
    """'cyrillic' | 'latin' | None (пусто/символы/смешанный >20% каждого)."""
    cyr = lat = 0
    for ch in (text or ""):
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF:                     # кириллический блок (вкл. Ёё)
            cyr += 1
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            lat += 1
    total = cyr + lat
    if total < MIN_LETTERS:
        return None
    if cyr / total > DOMINANCE:
        return "cyrillic"
    if lat / total > DOMINANCE:
        return "latin"
    return None


def _manifest_langs(advisor_dir):
    """Множество lang-кодов из sources/manifest.json (пустое, если нет/битый)."""
    mp = os.path.join(advisor_dir, "sources", "manifest.json")
    try:
        manifest = json.load(open(mp, encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(manifest, dict):
        return set()
    return {rec.get("lang", "").strip().lower()
            for rec in manifest.values()
            if isinstance(rec, dict) and rec.get("lang")}


def _script_of_lang(code):
    if code in CYRILLIC_LANGS:
        return "cyrillic"
    if code in LATIN_LANGS:
        return "latin"
    return None


def _infer_from_corpus(advisor_dir):
    """Скрипт по сэмплу первых чанков corpus.jsonl (majority по той же эвристике)."""
    cp = corpus_path(advisor_dir)
    if not os.path.isfile(cp):
        return None
    sample, n = [], 0
    try:
        with open(cp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    sample.append(json.loads(line).get("text", ""))
                except Exception:
                    continue
                n += 1
                if n >= SAMPLE_CHUNKS:
                    break
    except Exception:
        return None
    return script_of(" ".join(sample))


def corpus_script(advisor_dir):
    """Скрипт корпуса советника ('cyrillic'|'latin') или None (не определить → не флагуем).
    Источник: manifest lang (единогласный) → сэмпл чанков. Кэш — вывод один раз."""
    return _corpus_info(advisor_dir)[0]


def _corpus_info(advisor_dir):
    """(script|None, человекочитаемый lang-лейбл|None) с кэшем."""
    key = os.path.abspath(advisor_dir or "")
    if key in _CORPUS_CACHE:
        return _CORPUS_CACHE[key]
    script, label = None, None
    try:
        langs = _manifest_langs(advisor_dir)
        scripts = {_script_of_lang(l) for l in langs} - {None}
        if len(scripts) == 1:                          # манифест единогласен
            script = next(iter(scripts))
            label = "/".join(sorted(langs))
        else:                                          # нет манифеста / разнобой / незнакомый код
            script = _infer_from_corpus(advisor_dir)
            label = {"latin": "latin (вероятно English)", "cyrillic": "русский/кириллица"}.get(script)
    except Exception:
        script, label = None, None                     # детект НИКОГДА не валит retrieve/cite
    _CORPUS_CACHE[key] = (script, label)
    return script, label


def mismatch(query, advisor_dir):
    """None (нет мисматча / не определить) ИЛИ
    {"language_mismatch": True, "corpus_language": str, "language_directive": str}."""
    try:
        qs = script_of(query)
        if qs is None:
            return None
        cs, label = _corpus_info(advisor_dir)
        if cs is None or cs == qs:
            return None
        return {
            "language_mismatch": True,
            "corpus_language": label or cs,
            "language_directive": (
                "Запрос дан НЕ в ЯЗЫКЕ КОРПУСА этого советника (корпус: %s) — ретрив на "
                "кросс-языке тихо деградирует. ПЕРЕВЕДИ запрос на язык корпуса и повтори "
                "вызов (можно списком формулировок). Перевод — твой ризонинг, автоперевода "
                "нет." % (label or cs)),
        }
    except Exception:
        return None
