#!/usr/bin/env python3
"""
collect_common.py — общая база для сборщиков корпусов (collect_pd / collect_web / collect_transcript).

Принцип (ЛЕГАЛЬНАЯ ГРАНИЦА, см. SKILL.md):
  - сборщики НЕ дублируют пайплайн build_advisor.py; они легально НАПОЛНЯЮТ advisors/{name}/sources/
    текстом, дальше build_advisor.py делает чанкинг/провенанс/кандидаты-цитаты.
  - каждый файл получает provenance-заголовок (URL + дата + лицензия), чтобы fidelity-гейт и
    атрибуция знали происхождение.
  - public-domain тянется свободно; публичное-но-копирайтное (эссе/твиты/блоги/транскрипты) —
    только с явным подтверждением personal-use + дисклеймер «персона = симуляция».
  - большие тексты пишутся В ФАЙЛ, наружу печатается только сводка.
"""
import os, re, sys, json, urllib.request, datetime

UA = "Mozilla/5.0 (Consilium-Principis corpus collector; personal use)"

# Хосты, заведомо отдающие public-domain (для collect_pd авто-подтверждение PD).
PD_HOSTS = ("gutenberg.org", "www.gutenberg.org", "gutenberg.net",
            "wikisource.org", "standardebooks.org", "sacred-texts.com")


def today():
    return datetime.date.today().isoformat()


def host_of(url):
    m = re.match(r"https?://([^/]+)/?", url or "")
    return (m.group(1).lower() if m else "")


def is_pd_host(url):
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in PD_HOSTS)


def fetch(url, timeout=30):
    """GET → текст. Бросает понятное исключение при сетевой ошибке."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def html_to_text(html, selector=None):
    """HTML → читаемый текст. selector (CSS) — если задан, берём только этот контейнер."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        # грубый фолбэк без bs4
        txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        txt = re.sub(r"(?s)<[^>]+>", "\n", txt)
        return re.sub(r"\n{3,}", "\n\n", txt)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    node = soup.select_one(selector) if selector else (
        soup.select_one("article") or soup.select_one("main") or soup.body or soup)
    lines = [ln.strip() for ln in node.get_text("\n").splitlines()] if node else []
    return "\n".join(ln for ln in lines if ln)


def slugify(s):
    s = re.sub(r"[^\w\s-]", "", (s or "").lower(), flags=re.U)
    return re.sub(r"[\s_-]+", "-", s).strip("-")[:60] or "source"


def land_to_sources(advisor_dir, basename, text, *, url, license_note, extra_meta=None):
    """Пишет текст в advisors/{name}/sources/{basename}.txt с provenance-заголовком.
    Возвращает путь. sources/ — gitignored (чужие тексты в историю не уходят)."""
    src_dir = os.path.join(advisor_dir, "sources")
    os.makedirs(src_dir, exist_ok=True)
    path = os.path.join(src_dir, f"{slugify(basename)}.txt")
    header = [
        f"# SOURCE: {url}",
        f"# FETCHED: {today()}",
        f"# LICENSE: {license_note}",
    ]
    if extra_meta:
        for k, v in extra_meta.items():
            header.append(f"# {k.upper()}: {v}")
    header.append("# " + "-" * 60)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + "\n" + text.strip() + "\n")
    # сайдкар-манифест провенанса (для аудита; sources/ всё равно gitignored)
    man = os.path.join(src_dir, "_provenance.jsonl")
    with open(man, "a", encoding="utf-8") as f:
        rec = {"file": os.path.basename(path), "url": url, "fetched": today(),
               "license": license_note, "chars": len(text)}
        if extra_meta:
            rec.update(extra_meta)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def require_advisor_dir(advisor_dir):
    if not os.path.isdir(advisor_dir):
        print(f"Нет папки советника: {advisor_dir}", file=sys.stderr)
        sys.exit(1)


def summary(path, text, kind):
    print(f"  ✓ {kind}: {len(text)} симв (~{len(text)//4} токенов) → {path}")
    print(f"    дальше: python scripts/build_advisor.py {os.path.dirname(os.path.dirname(path))} "
          f"--name \"{{Имя}}\"  → corpus.jsonl + quote_candidates")
