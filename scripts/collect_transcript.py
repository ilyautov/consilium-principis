#!/usr/bin/env python3
"""
collect_transcript.py — сборщик транскриптов публичных выступлений/видео (напр. Munger talks).

ЛЕГАЛЬНАЯ ГРАНИЦА (серее, чем PD): сама речь публична, но права на КОНКРЕТНУЮ расшифровку/субтитры
могут принадлежать площадке. Тянем только публичные авто-субтитры для PERSONAL USE с атрибуцией и
дисклеймером. Требуется --personal-use. Платное/закрытое — не трогаем.

Источники:
  - YouTube: нужен пакет youtube-transcript-api (pip install youtube-transcript-api). Без него —
    скрипт честно говорит, как поставить, и не выдумывает текст.
  - Готовый транскрипт-URL (страница с текстом): --type page (через collect_web-механику).

Примеры:
  python scripts/collect_transcript.py advisors/munger --youtube VIDEO_ID --personal-use
  python scripts/collect_transcript.py advisors/munger --url https://.../transcript --type page --personal-use
"""
import sys, os, re, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_common as cc


def youtube_transcript(video_id, langs=("en", "ru")):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        print("❌ Нужен пакет: pip install youtube-transcript-api\n"
              "   (скрипт НЕ выдумывает транскрипт — только реальные субтитры).", file=sys.stderr)
        sys.exit(3)
    try:
        items = YouTubeTranscriptApi.get_transcript(video_id, languages=list(langs))
    except Exception as e:
        print(f"❌ Субтитры недоступны для {video_id}: {e}", file=sys.stderr)
        sys.exit(1)
    return "\n".join(it["text"].strip() for it in items if it.get("text", "").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisor_dir")
    ap.add_argument("--youtube", default=None, help="YouTube video id")
    ap.add_argument("--url", default=None, help="страница с готовым транскриптом (--type page)")
    ap.add_argument("--type", choices=["youtube", "page"], default="youtube")
    ap.add_argument("--name", default=None)
    ap.add_argument("--personal-use", action="store_true")
    args = ap.parse_args()
    cc.require_advisor_dir(args.advisor_dir)

    if not args.personal_use:
        print("❌ Транскрипт публичной речи для personal-use. Подтверди: --personal-use", file=sys.stderr)
        sys.exit(2)

    if args.youtube:
        url = f"https://www.youtube.com/watch?v={args.youtube}"
        text = youtube_transcript(args.youtube)
        basename = args.name or f"yt-{args.youtube}"
    elif args.url:
        url = args.url
        text = cc.html_to_text(cc.fetch(args.url))
        basename = args.name or cc.slugify(args.url.rsplit("/", 1)[-1] or "transcript")
    else:
        print("Дай --youtube VIDEO_ID или --url ... --type page", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    path = cc.land_to_sources(
        args.advisor_dir, basename, text, url=url,
        license_note="public-talk transcript (personal-use, attribution; transcript rights vary)",
        extra_meta={"disclaimer": "персона = симуляция; авто-субтитры могут содержать ошибки распознавания"})
    cc.summary(path, text, "transcript")


if __name__ == "__main__":
    main()
