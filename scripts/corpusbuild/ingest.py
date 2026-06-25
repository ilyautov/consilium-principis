"""Ингест: текст с позиционным провенансом + авто-детект кодировки (utf-8 → cp1251 → koi8-r → latin-1).
PDF/EPUB делегируем существующим экстракторам build_advisor (ленивый импорт)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_text_auto(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "cp1251", "koi8-r", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def extract_source(path: str):
    """→ [ (("line", n), text), ... ] для .txt/.md; для .pdf/.epub — провенанс page/chapter."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        lines = _read_text_auto(path).splitlines()
        return [(("line", i + 1), ln) for i, ln in enumerate(lines) if ln.strip()]
    import build_advisor
    if ext == ".pdf":
        return build_advisor.extract_pdf(path)
    if ext == ".epub":
        return build_advisor.extract_epub(path)
    return []
