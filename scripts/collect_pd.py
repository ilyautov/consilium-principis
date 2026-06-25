#!/usr/bin/env python3
"""
collect_pd.py — сборщик ПУБЛИЧНОГО ДОСТОЯНИЯ (Gutenberg / Wikisource / Standard Ebooks).

Тянет PD-текст и кладёт в advisors/{name}/sources/ с provenance-заголовком. Дальше — build_advisor.py.
PD-хосты (gutenberg.org, *.wikisource.org, standardebooks.org, sacred-texts.com) подтверждаются
автоматически; иной хост требует явного --license public-domain (ты подтверждаешь PD-статус сам).

Примеры:
  # «Размышления» Марка Аврелия, пер. George Long 1862 (Gutenberg #2680, public domain)
  python scripts/collect_pd.py advisors/marcus-aurelius --url https://www.gutenberg.org/cache/epub/2680/pg2680.txt
  python scripts/collect_pd.py advisors/x --url https://en.wikisource.org/wiki/... --license public-domain
"""
import sys, os, re, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_common as cc


def strip_gutenberg(text):
    """Убирает Gutenberg-обёртку (юридический хедер/футер не часть произведения)."""
    start = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text, re.I)
    end = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text, re.I)
    if start:
        text = text[start.end():]
    if end:
        text = text[:end.start() if not start else (end.start() - start.end())] if start else text[:end.start()]
    # повторный поиск end в уже обрезанном (если start был)
    end2 = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text, re.I)
    if end2:
        text = text[:end2.start()]
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisor_dir")
    ap.add_argument("--url", required=True)
    ap.add_argument("--name", default=None, help="имя файла-источника (slug)")
    ap.add_argument("--license", default=None,
                    help="подтверждение PD для не-PD-хоста: 'public-domain'")
    args = ap.parse_args()
    cc.require_advisor_dir(args.advisor_dir)

    # Легальный гейт: PD-хост ИЛИ явное подтверждение.
    if not cc.is_pd_host(args.url) and (args.license or "").lower() not in ("public-domain", "pd"):
        print(f"❌ Хост {cc.host_of(args.url)} не в списке заведомо-PD. Если текст ТОЧНО public domain,\n"
              f"   подтверди: --license public-domain. Иначе — это не для collect_pd "
              f"(копирайтное → collect_web с personal-use, либо не тянуть).", file=sys.stderr)
        sys.exit(2)

    print(f"PD-сборка: {args.url}")
    try:
        raw = cc.fetch(args.url)
    except Exception as e:
        print(f"❌ Не скачалось: {e}", file=sys.stderr)
        sys.exit(1)

    is_html = "<html" in raw[:2000].lower() or "wikisource" in args.url
    if is_html:
        selector = "#mw-content-text" if "wikisource" in args.url else None
        text = cc.html_to_text(raw, selector=selector)
    else:
        text = raw
    if "gutenberg" in args.url.lower():
        text = strip_gutenberg(text)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 500:
        print(f"⚠️ Подозрительно мало текста ({len(text)} симв) — проверь URL/селектор.", file=sys.stderr)

    basename = args.name or cc.slugify(args.url.rsplit("/", 1)[-1] or "pd-source")
    path = cc.land_to_sources(args.advisor_dir, basename, text,
                              url=args.url, license_note="public-domain")
    cc.summary(path, text, "public-domain")


if __name__ == "__main__":
    main()
