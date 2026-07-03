"""Каталог PD-фигур (указатели, ноль текста) + оркестрация сборки советника из общественного
достояния. Сеть/сборка инъектируются (fetch=/build=) → всё оффлайн-тестируемо. Логика в сервере,
хост только предлагает и рисует. Firewall: каталог = указатели, корпус — локально в advisors/*."""
import os, json, hashlib

ALLOWED_PLATFORMS = {"gutenberg", "standardebooks", "wikisource"}


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
        "kind": "pd_preview", "figure": name, "edition": edition, "pd_basis": pd_basis,
        "bytes": len(stripped.encode("utf-8")), "sha256": text_sha256(stripped),
        "sample": sample, "pd_host_ok": pd_ok, "warnings": warnings,
        "confirm_hint": "Собрать советника локально из этого издания?",
    }
