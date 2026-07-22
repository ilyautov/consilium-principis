#!/usr/bin/env python3
"""Ингест публичного Telegram-канала → корпус Принцепса (твои слова = P1 твоей персоны).

Симметрия с советниками: их персону строим из их текстов, тебя — из твоих. Посты публичного
канала берём через web-превью t.me/s/<handle> (stdlib, без зависимостей). Запись — в приватный
principis_corpus/ (gitignored, личные данные). Тир = P1 (это ТВОИ слова, не комментарий).

ОГРАНИЧЕНИЯ v0 (чинить осознанно):
- t.me/s/ отдаёт только ПОСТЫ, не комменты (комменты — в связанном discussion-чате, нужен др. путь).
- Без пагинации берёт только последнюю страницу (свежие посты). Полная история — через ?before=<id> (TODO).
- Работает только для ПУБЛИЧНОГО канала.

Использование:  python scripts/ingest_telegram.py <@handle|handle> [out.jsonl]
"""
import os
import re
import sys
import json
import html as _html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MSG_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)


def parse_telegram_html(page_html):
    """HTML страницы t.me/s/<handle> → список текстов постов (теги сняты, <br>→\\n, entity раскрыты)."""
    posts = []
    for raw in MSG_RE.findall(page_html):
        t = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)   # переносы строк
        t = re.sub(r"<[^>]+>", "", t)                       # снять прочие теги
        t = _html.unescape(t)                               # &amp; &quot; &#128512; …
        t = re.sub(r"[ \t]+\n", "\n", t).strip()            # хвостовые пробелы
        if len(t) >= 12:                                    # отсечь пустые/служебные
            posts.append(t)
    return posts


def posts_to_records(posts, handle):
    """Посты → corpus-записи (тир P1 — ТВОИ слова; источник = telegram:<handle>)."""
    h = handle.lstrip("@")
    return [{"source": f"telegram:{h}", "tier": "P1", "text": p} for p in posts]


def _write_corpus_exclusive(records, out_path):
    """Создать новый corpus-файл без TOCTOU между проверкой имени и записью."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    directory, filename = os.path.split(out_path)
    stem, extension = os.path.splitext(filename)
    match = re.match(r"^(.*)-(\d+)$", stem)
    base = match.group(1) if match else stem
    number = int(match.group(2)) if match else 1
    while True:
        candidate_name = (filename if number == 1 else "%s-%d%s" % (base, number, extension))
        candidate = os.path.join(directory, candidate_name)
        try:
            with open(candidate, "x", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            return len(records), candidate
        except FileExistsError:
            number += 1


def write_corpus(records, out_path):
    """Записать corpus в новый файл, выбирая числовой суффикс при коллизии."""
    written, _path = _write_corpus_exclusive(records, out_path)
    return written


def _safe_handle(handle):
    """Telegram-handle: только [A-Za-z0-9_], 1..64 симв. Режет инъекцию в URL-путь
    (слэши/CRLF/query) — handle приходит из аргументов хоста (возможна инъекция)."""
    h = re.sub(r"[^A-Za-z0-9_]", "", (handle or "").lstrip("@"))
    if not h:
        raise ValueError("пустой/недопустимый telegram handle")
    return h[:64]


def _fetch_channel_html_canonical(canonical_handle, timeout=20):
    """Скачать preview уже канонического публичного Telegram handle."""
    from collect_common import fetch as _cc_fetch
    return _cc_fetch(f"https://t.me/s/{canonical_handle}", timeout=timeout)


def fetch_channel_html(handle, timeout=20):
    """Скачать web-превью публичного канала через collect_common.fetch — тот же SSRF-гард
    (схема/публичный IP/ре-валидация редиректов), что у add_source. Сеть нужна (sandbox может
    блокировать — тогда агент отдаёт HTML через WebFetch в parse_telegram_html напрямую)."""
    return _fetch_channel_html_canonical(_safe_handle(handle), timeout=timeout)


def ingest(handle, out_path=None):
    out_path = out_path or os.path.join("principis_corpus", "telegram.jsonl")
    canonical_handle = _safe_handle(handle)
    posts = parse_telegram_html(_fetch_channel_html_canonical(canonical_handle))
    n, final_path = _write_corpus_exclusive(posts_to_records(posts, canonical_handle), out_path)
    return {"handle": canonical_handle, "posts": len(posts), "out": final_path, "written": n}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    res = ingest(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"[telegram] @{res['handle']}: {res['posts']} постов → {res['out']}")
    if res["posts"] == 0:
        print("0 постов — канал приватный/пуст, неверный handle, или сеть заблокирована sandbox.")
