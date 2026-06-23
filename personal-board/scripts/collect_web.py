#!/usr/bin/env python3
"""
collect_web.py — сборщик ПУБЛИЧНОГО веб-контента живых/недавних фигур: эссе, блоги, твиты,
публичные Telegram-каналы.

ЛЕГАЛЬНАЯ ГРАНИЦА: контент публичный, но КОПИРАЙТНЫЙ (принадлежит автору). Тянем только для
PERSONAL USE с дисклеймером «персона = симуляция» и сохранением атрибуции. Требуется явный
флаг --personal-use (осознанное подтверждение). Платное/за-пейволлом не тянуть.

Типы (--type):
  blog | essay   — статья/страница (article/main → читаемый текст)
  telegram       — публичный канал: t.me/s/{channel} (веб-превью) или t.me/{channel}/{id}

Примеры:
  python scripts/collect_web.py advisors/naval --type essay --url https://nav.al/rich --personal-use
  python scripts/collect_web.py advisors/x --type telegram --url https://t.me/s/durov --personal-use
"""
import sys, os, re, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_common as cc


def extract_telegram(html):
    """Публичный t.me/s/{channel} → тексты сообщений. Без приватных каналов и без API."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return cc.html_to_text(html)
    soup = BeautifulSoup(html, "html.parser")
    msgs = soup.select("div.tgme_widget_message_text")
    if not msgs:  # одиночный пост или иная разметка
        return cc.html_to_text(html, selector="div.tgme_widget_message_text") or cc.html_to_text(html)
    return "\n\n".join(m.get_text("\n").strip() for m in msgs if m.get_text(strip=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisor_dir")
    ap.add_argument("--url", required=True)
    ap.add_argument("--type", choices=["blog", "essay", "telegram"], default="essay")
    ap.add_argument("--name", default=None)
    ap.add_argument("--personal-use", action="store_true",
                    help="ОБЯЗАТЕЛЬНО: подтверждаю personal-use копирайтного публичного контента")
    args = ap.parse_args()
    cc.require_advisor_dir(args.advisor_dir)

    if not args.personal_use:
        print("❌ Это копирайтный публичный контент. Подтверди осознанно: --personal-use\n"
              "   (персона = симуляция, атрибуция сохраняется, дистрибуция требует согласия автора).",
              file=sys.stderr)
        sys.exit(2)

    print(f"web-сборка [{args.type}]: {args.url}")
    try:
        raw = cc.fetch(args.url)
    except Exception as e:
        print(f"❌ Не скачалось: {e}", file=sys.stderr)
        sys.exit(1)

    if args.type == "telegram":
        text = extract_telegram(raw)
    else:
        text = cc.html_to_text(raw)  # article/main эвристика внутри
    text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if len(text) < 200:
        print(f"⚠️ Мало текста ({len(text)} симв) — проверь URL/тип (динамические страницы могут "
              f"не отдавать контент без JS).", file=sys.stderr)

    basename = args.name or cc.slugify(args.url.replace("https://", "").replace("/", "-"))
    path = cc.land_to_sources(
        args.advisor_dir, basename, text, url=args.url,
        license_note="public-web (copyrighted, personal-use, attribution required)",
        extra_meta={"type": args.type, "disclaimer": "персона = симуляция, не вердикт реального лица"})
    cc.summary(path, text, f"public-web/{args.type}")


if __name__ == "__main__":
    main()
