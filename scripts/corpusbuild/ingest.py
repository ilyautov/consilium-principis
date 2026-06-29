"""Ингест: текст с позиционным провенансом + авто-детект кодировки (utf-8 → cp1251 → koi8-r → latin-1).
PDF/EPUB делегируем существующим экстракторам build_advisor (ленивый импорт)."""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SEP_RE = re.compile(r"^#\s*-{6,}\s*$")


def _read_text_auto(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "cp1251", "koi8-r", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _provenance_header_span(lines):
    """Сколько ведущих строк занимает provenance-заголовок land_to_sources
    (# SOURCE: … / # FETCHED / # LICENSE / # ------). 0, если первая строка — НЕ наша
    сигнатура `# SOURCE:` (markdown-заголовки `# Heading` не трогаем). Иначе — индекс ПОСЛЕ
    разделительной `# -----` строки. Без разделителя считаем формат чужим и не режем."""
    if not lines or not lines[0].startswith("# SOURCE:"):
        return 0
    for i, ln in enumerate(lines):
        if _SEP_RE.match(ln):
            return i + 1
    return 0


def extract_source(path: str):
    """→ [ (("line", n), text), ... ] для .txt/.md; для .pdf/.epub — провенанс page/chapter.
    Provenance-заголовок (метаданные источника) вырезается — он живёт в _provenance.jsonl и
    не должен попадать в корпус/цитаты (иначе `# SOURCE: …` цитировался бы как 🔵)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        lines = _read_text_auto(path).splitlines()
        skip = _provenance_header_span(lines)        # абсолютные номера строк сохраняем
        return [(("line", i + 1), ln) for i, ln in enumerate(lines)
                if i >= skip and ln.strip()]
    import build_advisor
    if ext == ".pdf":
        return build_advisor.extract_pdf(path)
    if ext == ".epub":
        return build_advisor.extract_epub(path)
    return []
