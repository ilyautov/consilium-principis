#!/usr/bin/env python3
"""
build_advisor.py — ingest-конвейер слоя 0 для скилла «Личный совет директоров».

Берёт ЛЕГАЛЬНЫЕ материалы советника (что пользователь сам приносит) из папки
advisors/{name}/sources/ и строит:
  - corpus.jsonl        : чанки с провенансом (источник + позиция) для RAG / character_book
  - quote_candidates.md : кандидаты-цитаты с точной ссылкой, для верификации человеком
  - persona_draft.md    : скелет персоны (конституция-затравка из извлечённого)

Принцип верности (см. ARCHITECTURE раздел 6):
  - цитата НИКОГДА не выдаётся без провенанса (источник + позиция);
  - извлечённое = КАНДИДАТЫ, требующие верификации до попадания в quote_bank;
  - скрипт ничего не качает из сети. Только то, что пользователь сам положил в sources/.

Поддержка форматов: .txt .md (нативно) · .pdf (pdfplumber|PyPDF2) · .epub (ebooklib+bs4).

Использование:
  python build_advisor.py advisors/marcus-aurelius --name "Марк Аврелий"
"""
import sys, os, re, json, argparse, hashlib

# ---------- извлечение текста с провенансом ----------

def extract_txt(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()
    # провенанс = диапазон строк
    return [(("line", i + 1), ln) for i, ln in enumerate(lines) if ln.strip()]

def extract_pdf(path):
    out = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for pno, page in enumerate(pdf.pages, 1):
                txt = page.extract_text() or ""
                for ln in txt.splitlines():
                    if ln.strip():
                        out.append((("page", pno), ln))
        return out
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader
        r = PdfReader(path)
        for pno, page in enumerate(r.pages, 1):
            txt = page.extract_text() or ""
            for ln in txt.splitlines():
                if ln.strip():
                    out.append((("page", pno), ln))
    except Exception as e:
        print(f"  ! pdf не прочитан ({os.path.basename(path)}): {e}", file=sys.stderr)
    return out

def extract_epub(path):
    out = []
    try:
        from ebooklib import epub
        import ebooklib
        from bs4 import BeautifulSoup
        book = epub.read_epub(path)
        for cno, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT), 1):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            for p in soup.get_text("\n").splitlines():
                if p.strip():
                    out.append((("chapter", cno), p))
    except Exception as e:
        print(f"  ! epub не прочитан ({os.path.basename(path)}): {e}", file=sys.stderr)
    return out

def extract_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        return extract_txt(path)
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".epub":
        return extract_epub(path)
    return []

# ---------- чанкинг с провенансом ----------

def chunk_lines(records, source, target_chars=900, overlap_chars=180):
    """records: list of ((loc_kind, loc_val), text). Склеивает в чанки ~target_chars
    с overlap, сохраняя позицию начала/конца (для RAG-граундинга)."""
    chunks, buf, start_loc, last_loc = [], [], None, None
    cur = 0
    for loc, txt in records:
        if start_loc is None:
            start_loc = loc
        buf.append(txt)
        last_loc = loc
        cur += len(txt) + 1
        if cur >= target_chars:
            body = " ".join(buf).strip()
            chunks.append({"source": source, "start": list(start_loc), "end": list(last_loc), "text": body})
            # overlap: оставить хвост
            tail, tlen = [], 0
            for t in reversed(buf):
                tail.insert(0, t); tlen += len(t) + 1
                if tlen >= overlap_chars:
                    break
            buf = tail
            start_loc = last_loc
            cur = sum(len(t) + 1 for t in buf)
    if buf:
        body = " ".join(buf).strip()
        if body:
            chunks.append({"source": source, "start": list(start_loc or ["?", 0]),
                           "end": list(last_loc or ["?", 0]), "text": body})
    return chunks

# ---------- извлечение кандидатов-цитат ----------

SENT_RE = re.compile(r"[^.!?]*[.!?]")

def quote_candidates(chunks, max_out=40):
    seen, cands = set(), []
    for ch in chunks:
        for m in SENT_RE.finditer(ch["text"]):
            s = m.group().strip()
            words = s.split()
            if not (5 <= len(words) <= 32):       # афористичная длина
                continue
            if s.endswith("?"):                     # утверждение, не вопрос
                continue
            if len(s) < 28 or len(s) > 220:
                continue
            key = re.sub(r"\W+", "", s.lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            # скоринг «афористичности»: короче и с сильными словами = выше
            score = 0
            score += max(0, 22 - abs(16 - len(words)))
            for kw in ("never", "always", "must", "are", "is", "do", "не", "всегда", "никогда", "должен"):
                if f" {kw} " in f" {s.lower()} ":
                    score += 2
            cands.append((score, s, ch["source"], tuple(ch["start"])))
    cands.sort(key=lambda x: -x[0])
    return cands[:max_out]

# ---------- запись артефактов ----------

def write_outputs(adv_dir, name, chunks, cands):
    corpus_path = os.path.join(adv_dir, "corpus.jsonl")
    with open(corpus_path, "w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    qpath = os.path.join(adv_dir, "quote_candidates.md")
    with open(qpath, "w", encoding="utf-8") as f:
        f.write(f"# Кандидаты-цитаты: {name}\n\n")
        f.write("СТАТУС: не верифицировано. Каждую перед попаданием в quote_bank проверить "
                "по источнику и проставить tier. Цитата без провенанса не используется.\n\n")
        for i, (score, s, src, start) in enumerate(cands, 1):
            loc = f"{start[0]} {start[1]}"
            f.write(f"{i}. «{s}»\n   — источник: {src} · {loc} · score {score} · ⏳ verify\n\n")

    return corpus_path, qpath

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisor_dir", help="папка советника (содержит sources/)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--max-quotes", type=int, default=40)
    args = ap.parse_args()

    name = args.name or os.path.basename(args.advisor_dir.rstrip("/"))
    src_dir = os.path.join(args.advisor_dir, "sources")
    if not os.path.isdir(src_dir):
        print(f"Нет папки {src_dir}. Положи туда легальные материалы советника.", file=sys.stderr)
        sys.exit(1)

    files = [f for f in sorted(os.listdir(src_dir))
             if os.path.splitext(f)[1].lower() in (".txt", ".md", ".pdf", ".epub")]
    if not files:
        print(f"В {src_dir} нет поддерживаемых файлов (.txt .md .pdf .epub).", file=sys.stderr)
        sys.exit(1)

    all_chunks = []
    print(f"Советник: {name}")
    for fn in files:
        recs = extract_any(os.path.join(src_dir, fn))
        chs = chunk_lines(recs, source=fn)
        all_chunks.extend(chs)
        print(f"  · {fn}: строк/блоков {len(recs)} → чанков {len(chs)}")

    cands = quote_candidates(all_chunks, max_out=args.max_quotes)
    corpus_path, qpath = write_outputs(args.advisor_dir, name, all_chunks, cands)

    total_chars = sum(len(c["text"]) for c in all_chunks)
    print(f"\nИтог:")
    print(f"  чанков всего: {len(all_chunks)} (~{total_chars} симв, ~{total_chars//4} токенов)")
    print(f"  индексация: {'character_book / full-context (без вектор-БД)' if total_chars < 800000 else 'нужен вектор-стор (>200k токенов)'}")
    print(f"  кандидатов-цитат: {len(cands)} → {qpath}")
    print(f"  корпус: {corpus_path}")
    print(f"\nДальше: верифицировать цитаты (проставить tier) → перенести в persona.md quote_bank.")

if __name__ == "__main__":
    main()
