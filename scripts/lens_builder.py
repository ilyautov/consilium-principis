"""Интерактивный билдер линз (направление «линзы > личности», внутренний дизайн-док). Линза = advisor-каталог; строится тем же corpusbuild.pipeline. Три конфигурации
заземления через ТИРЫ (правки контура не нужны — гейт fail-closed):

  • текст-основа (`ground_text`) → тир P1 → 🔵 дословные слова авторитета линзы:
      personality → слова автора (его PD-текст);  self → ТВОИ слова;  method → текст метода/статьи.
  • заметки-прочтение (`reading_notes`) → тир U1 → НЕ P1/P2 → гейт даёт 🟡 (твоя интерпретация,
    не выдаётся за слова автора). Так «Макиавелли — как читаю я» честен: 🔵 его, 🟡 твоё.

Интервью («как ТЫ его читаешь?») ведёт хост (см. instructions); тут — чистый коммит в каталог.
"""
import os
import json
import collections

from corpusbuild import pipeline, paths

_KIND_FRAME = {
    "personality": "линза-поверх-личности — прочтение мыслителя ТОБОЙ (его дословные слова = 🔵, "
                   "твоя интерпретация = 🟡). НЕ цифровой двойник: имя сигналит «как читаю я».",
    "method":      "линза метода/подхода — заземлена на текст метода (статьи/доки). Цитирует 🔵.",
    "self":        "линза себя — твои собственные слова как авторитет твоей персоны (🔵), "
                   "как Telegram-ингест Принцепса.",
}


def _manifest(has_notes):
    m = {"ground.txt": {"tier": "P1", "note": "Дословный текст-основа линзы (слова авторитета)."}}
    if has_notes:
        m["reading.md"] = {"tier": "U1", "note": "Твоё прочтение/интерпретация — НЕ слова автора (→ 🟡)."}
    return m


def _lens_md(name, kind, axis, reading_notes):
    frame = _KIND_FRAME.get(kind, _KIND_FRAME["personality"])
    out = ["---", f"name: {name}", "grade: grounded-lens", "marker_ceiling: 🔵"]
    if axis:
        out.append(f"axis: {axis}")
    out += ["kind: " + kind, "---", "", f"# {name} — grounded-линза", "", f"> {frame}", ""]
    if reading_notes:
        out += ["## Как читаю (твой слой — 🟡, не слова автора)", "", reading_notes.strip(), ""]
    out += ["## Контур", "",
            "🔵 — дословно из текста-основы (тир P1); 🟡 — твоё прочтение (тир U1) или экстраполяция. "
            "Заметки-интерпретация НИКОГДА не выдаются за дословные слова автора.", ""]
    return "\n".join(out)


def build_lens(dest, name, ground_text, reading_notes=None, author=None,
               kind="personality", axis=None, run_kernels=False, built_at="unknown"):
    """Собрать grounded-линзу в каталоге `dest` (абсолютный путь). Возвращает сводку.
    ground_text → P1 (🔵), reading_notes → U1 (🟡). run_kernels — best-effort (нужен ollama)."""
    if not ground_text or not ground_text.strip():
        raise ValueError("ground_text пуст — линзе нужна дословная основа (иначе 🔵 неоткуда взяться)")
    src = os.path.join(dest, "sources")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "ground.txt"), "w", encoding="utf-8") as f:
        f.write(ground_text.strip() + "\n")
    has_notes = bool(reading_notes and reading_notes.strip())
    if has_notes:
        with open(os.path.join(src, "reading.md"), "w", encoding="utf-8") as f:
            f.write(reading_notes.strip() + "\n")
    with open(os.path.join(src, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(_manifest(has_notes), f, ensure_ascii=False, indent=2)

    chunks = pipeline.build(dest, built_at=built_at)              # ingest→clean(tier)→chunk→build/corpus.jsonl

    with open(os.path.join(dest, "lens.md"), "w", encoding="utf-8") as f:
        f.write(_lens_md(name, kind, axis, reading_notes))

    kernels_ran = False
    if run_kernels:
        try:                                                     # best-effort: kernels нужен ollama
            from corpusbuild import kernels as _k
            _k.build_kernels(dest, author or name)
            kernels_ran = True
        except Exception:
            kernels_ran = False

    tiers = collections.Counter(c.get("tier", "?") for c in chunks)
    return {"dir": dest, "name": name, "kind": kind, "n_chunks": len(chunks),
            "tiers": dict(tiers), "kernels_ran": kernels_ran,
            "corpus": paths.corpus_path(dest)}     # через резолвер, не литерал
