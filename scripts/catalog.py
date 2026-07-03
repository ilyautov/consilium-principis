"""Каталог PD-фигур (указатели, ноль текста) + оркестрация сборки советника из общественного
достояния. Сеть/сборка инъектируются (fetch=/build=) → всё оффлайн-тестируемо. Логика в сервере,
хост только предлагает и рисует. Firewall: каталог = указатели, корпус — локально в advisors/*."""
import os, json, hashlib, re
import urllib.parse

ALLOWED_PLATFORMS = {"gutenberg", "standardebooks", "wikisource"}

_SAFE_FID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _safe_advisor_dir(root, fid):
    """→ (adv_dir, None) если fid безопасен и путь реально под root/advisors; иначе (None, error-строка).
    Fail-closed: charset-гард + realpath-assert (defense-in-depth, как _resolve_under_root)."""
    if not fid or not _SAFE_FID.match(fid) or ".." in fid:
        return None, f"небезопасный id/fid: {fid!r}"
    base = os.path.realpath(os.path.join(root, "advisors"))
    adv = os.path.realpath(os.path.join(base, fid))
    if adv != base and not adv.startswith(base + os.sep):
        return None, "путь вне advisors/ (traversal)"
    return adv, None


def load_catalog(root):
    """Читает <root>/catalog/pd_figures.json. Нет файла → пустой каталог (fail-closed, не падение)."""
    p = os.path.join(root, "catalog", "pd_figures.json")
    if not os.path.exists(p):
        return {"version": 1, "figures": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def validate_catalog(data):
    """→ список человеческих ошибок ([] = валиден). Fail-closed: кривая запись глушит фигуру."""
    errs = []
    if not isinstance(data, dict) or not isinstance(data.get("figures"), list):
        return ["каталог: нет списка figures"]
    seen = set()
    for i, fig in enumerate(data["figures"]):
        tag = fig.get("id", f"#{i}")
        if not fig.get("id") or not fig.get("name"):
            errs.append(f"{tag}: нет id или name")
        fid = fig.get("id")
        if fid and (".." in fid or not _SAFE_FID.match(fid)):
            errs.append(f"{tag}: небезопасный id")
        if fig.get("id") in seen:
            errs.append(f"{tag}: дублирующийся id")
        seen.add(fig.get("id"))
        src = fig.get("source")
        if not isinstance(src, dict) or not src.get("url"):
            errs.append(f"{tag}: нет source.url")
            continue
        if src.get("platform") not in ALLOWED_PLATFORMS:
            errs.append(f"{tag}: платформа '{src.get('platform')}' не в whitelist {sorted(ALLOWED_PLATFORMS)}")
    return errs


def get_figure(data, fid):
    for fig in data.get("figures", []):
        if fig.get("id") == fid:
            return fig
    return None


def strip_for_signature(raw):
    """Текст ПОСЛЕ снятия Gutenberg-обёртки — детерминированная основа подписи и сборки."""
    import collect_pd
    return collect_pd.strip_gutenberg(raw).strip()


def text_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_signature(stripped, expected):
    """→ (ok, actual_sha, reason). expected None → bootstrap (ok, но помечаем «не посеяна»).
    Есть expected.sha256 и не сошлось → fail-closed (текст уплыл — не собираем молча)."""
    actual = text_sha256(stripped)
    if not expected or not expected.get("sha256"):
        return True, actual, "подпись не посеяна (bootstrap) — прогони catalog_verify --seed"
    if actual != expected["sha256"]:
        return False, actual, "подпись не сошлась: издание на источнике изменилось (fail-closed)"
    return True, actual, "ok"


def _ocr_noise_ratio(text):
    if not text:
        return 1.0
    junk = sum(1 for c in text if not (c.isalnum() or c.isspace() or c in ".,;:!?—-–'\"()«»"))
    return junk / len(text)


def build_preview(*, name, edition, pd_basis, url, raw):
    """Render-agnostic превью-объект: один dict → адаптеры рендера (Cowork-виджет/текст/чужой агент)."""
    import collect_common as cc
    stripped = strip_for_signature(raw)
    sample = stripped[:400]
    warnings = []
    ratio = _ocr_noise_ratio(stripped[:2000])
    if ratio > 0.15:
        warnings.append(f"возможен OCR-шум/низкое качество (доля не-текст. символов {ratio:.0%})")
    pd_ok = cc.is_pd_host(url)
    if not pd_ok:
        warnings.append("хост не в PD-whitelist — потребуется явный license=public-domain")
    return {
        "ok": True,
        "kind": "pd_preview", "figure": name, "edition": edition, "pd_basis": pd_basis,
        "bytes": len(stripped.encode("utf-8")), "sha256": text_sha256(stripped),
        "sample": sample, "pd_host_ok": pd_ok, "warnings": warnings,
        "confirm_hint": "Собрать советника локально из этого издания?",
    }


def _resolve_ref(ref, root):
    """id из каталога → (name, edition, pd_basis, url, expected); голый url → минимальная запись."""
    if ref.startswith("http://") or ref.startswith("https://"):
        return {"name": ref, "edition": "", "pd_basis": "", "url": ref, "expected": None}
    fig = get_figure(load_catalog(root), ref)
    if not fig:
        return None
    s = fig.get("source")
    if not fig.get("name") or not isinstance(s, dict) or not s.get("url"):
        return None  # кривая запись → как «нет в каталоге» (callers отдают error-dict)
    return {"name": fig["name"], "edition": s.get("edition", ""), "pd_basis": s.get("pd_basis", ""),
            "url": s["url"], "expected": s.get("expected")}


def preview_source(ref, *, root, fetch):
    r = _resolve_ref(ref, root)
    if r is None:
        return {"ok": False, "error": f"нет фигуры '{ref}' в каталоге"}
    raw = _decode(fetch(r["url"]))
    return build_preview(name=r["name"], edition=r["edition"], pd_basis=r["pd_basis"],
                         url=r["url"], raw=raw)


def add_from_catalog(ref, *, root, license, fetch, build):
    """Мутирующий: fetch → strip → verify подпись (fail-closed) → land → build. Rule 0 (согласие) —
    на уровне хоста (превью-карточка перед вызовом). Собирает в <root>/advisors/<id> локально."""
    import collect_common as cc
    r = _resolve_ref(ref, root)
    if r is None:
        return {"ok": False, "error": f"нет фигуры '{ref}' в каталоге"}
    if not cc.is_pd_host(r["url"]) and license != "public-domain":
        return {"ok": False, "error": "не-PD хост требует license=public-domain (подтверди PD-статус сам)"}
    raw = _decode(fetch(r["url"]))
    stripped = strip_for_signature(raw)
    ok, actual, reason = verify_signature(stripped, r["expected"])
    if not ok:
        return {"ok": False, "error": reason, "actual_sha256": actual}
    is_url = ref.startswith("http://") or ref.startswith("https://")
    fid = cc.slugify(r["name"]) if is_url else ref
    adv_dir, err = _safe_advisor_dir(root, fid)
    if err:
        return {"ok": False, "error": err}
    if len(stripped.strip()) < 200:
        return {"ok": False, "error": "источник пуст/слишком короткий — не собираю мусор"}
    os.makedirs(os.path.join(adv_dir, "sources"), exist_ok=True)
    cc.land_to_sources(adv_dir, fid, stripped, url=r["url"],
                       license_note=r["pd_basis"] or "public-domain")
    build(adv_dir, built_at=cc.today())
    return {"ok": True, "advisor": adv_dir, "sha256": actual, "note": reason}


def _decode(raw):
    return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")


def verify_catalog(root, *, fetch, seed=False):
    """Обойти каталог: fetch → strip → сверить подпись/PD-basis. seed=True → записать sha256 в записи.
    → {ok, entries:[{id, status: ok|drift|unseeded|seeded|error, ...}]}. Ритуал целостности (как moat-check)."""
    data = load_catalog(root)
    entries, all_ok = [], True
    changed = False
    for fig in data.get("figures", []):
        src = fig.get("source", {})
        try:
            stripped = strip_for_signature(_decode(fetch(src["url"])))
        except Exception as e:
            entries.append({"id": fig.get("id"), "status": "error", "detail": str(e)}); all_ok = False
            continue
        actual = text_sha256(stripped)
        if seed:
            src["expected"] = {"sha256": actual, "bytes": len(stripped.encode("utf-8"))}
            changed = True
            entries.append({"id": fig.get("id"), "status": "seeded", "sha256": actual})
            continue
        exp = (src.get("expected") or {}).get("sha256")
        if not exp:
            entries.append({"id": fig.get("id"), "status": "unseeded"}); all_ok = False
        elif exp != actual:
            entries.append({"id": fig.get("id"), "status": "drift", "expected": exp, "actual": actual})
            all_ok = False
        else:
            entries.append({"id": fig.get("id"), "status": "ok"})
    if changed:
        with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return {"ok": all_ok, "entries": entries}


def search_gutenberg(author, *, fetch):
    """Кандидаты-издания из gutendex.com (JSON API PG). Хвост вне каталога. Оффлайн → error, не краш."""
    url = "https://gutendex.com/books?search=" + urllib.parse.quote(author)
    try:
        data = json.loads(_decode(fetch(url)))
    except Exception as e:
        return {"ok": False, "error": f"поиск недоступен (оффлайн?): {e}", "candidates": []}
    if not isinstance(data, dict):
        return {"ok": False, "error": "неожиданный ответ поиска", "candidates": []}
    out = []
    for b in data.get("results", [])[:8]:
        txt = next((v for k, v in (b.get("formats") or {}).items()
                    if "text/plain" in k and isinstance(v, str) and v.endswith(".txt")), None)
        if txt:
            out.append({"gutenberg_id": b.get("id"), "title": b.get("title"),
                        "authors": [a.get("name") for a in b.get("authors", [])],
                        "url": txt, "pd_basis": "Project Gutenberg (US-PD)"})
    return {"ok": True, "candidates": out}
