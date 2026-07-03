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
