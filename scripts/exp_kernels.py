#!/usr/bin/env python3
"""L2-эксперимент: извлечь мета-идеи (кернелы) и провалидировать ФАЛЬСИФИЦИРУЕМО.

Гипотеза (spec L2.4): кернел валиден, если выведенный из ЧАСТИ корпуса он объясняет ОТЛОЖЕННЫЕ
пассажи лучше случайного — И дискриминативно (кернелы советника X объясняют held-out X лучше,
чем кернелы советника Y). Иначе это общая мудрость / литературщина, не модель мыслителя.

Метод:
  1. P1-тело корпуса (фронт-маттер переводчика отрезаем) → split train/held-out (детерминир.).
  2. extract: gemma3:27b из сэмпла train-пассажей → 5-7 кернелов (имя + порождающий МЕТОД).
  3. validate (объективно, без LLM-судьи): embed(kernel) vs embed(held-out passage) через bge-m3.
     Для каждого held-out пассажа X: max-cos к своим кернелам vs к чужим. own_win = свой > чужой.
  4. Бином-тест own-win-rate vs 50%. Дискриминация в ОБЕ стороны = кернелы реальны и специфичны.

Модели: KERNEL_MODEL (extract, дефолт gemma3:27b — качество), EMBED_MODEL (bge-m3).
"""
import os, sys, json, re, urllib.request, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpusbuild.paths import corpus_path

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
KERNEL_MODEL = os.getenv("KERNEL_MODEL", "gemma3:27b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
AUTHORS = {"marcus-aurelius": "Marcus Aurelius", "machiavelli": "Niccolò Machiavelli"}


def load_manifest(adv):
    p = f"{adv}/sources/manifest.json"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def p1_body(slug):
    """P1-чанки тела: исключаем не-P1 (Тарасов) по манифесту и фронт-маттер переводчика."""
    adv = f"advisors/{slug}"
    man = load_manifest(adv)
    chunks = [json.loads(l) for l in open(corpus_path(adv), encoding="utf-8") if l.strip()]
    # тир по источнику: с манифестом — берём только P1; без — всё P1 (бэк-компат)
    chunks = [c for c in chunks if (man.get(c["source"], {}).get("tier", "P1") == "P1")]
    # отрезать фронт-маттер: с первого вхождения маркера начала тела
    markers = {"marcus-aurelius": "THE FIRST BOOK", "machiavelli": "CHAPTER I"}
    mk = markers.get(slug)
    if mk:
        start = next((i for i, c in enumerate(chunks) if mk in c["text"].upper()), 0)
        chunks = chunks[start:]
    return [c for c in chunks if len(c.get("text", "")) > 250]


def split(chunks):
    train = [c for i, c in enumerate(chunks) if i % 3 != 0]
    held = [c for i, c in enumerate(chunks) if i % 3 == 0]
    return train, held


def embed(texts, batch=64):
    out = []
    for i in range(0, len(texts), batch):
        body = json.dumps({"model": EMBED_MODEL, "input": texts[i:i + batch]}).encode()
        req = urllib.request.Request(f"{OLLAMA}/api/embed", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            embs = json.loads(r.read())["embeddings"]
        out.extend(embs)
    # нормализация
    norm = []
    for v in out:
        s = math.sqrt(sum(x * x for x in v)) or 1.0
        norm.append([x / s for x in v])
    return norm


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def extract_kernels(author, train, k=6, n_sample=28):
    step = max(1, len(train) // n_sample)
    sample = [train[i]["text"][:320].strip() for i in range(0, len(train), step)][:n_sample]
    passages = "\n---\n".join(sample)
    prompt = (
        f"You are analyzing the writings of {author}. Below are passages sampled from the corpus.\n"
        f"Identify the {k} META-IDEAS (generative kernels) that GENERATE these and the author's other "
        "writings — the recurring THINKING METHODS and core principles running through everything, NOT "
        "surface topics. For each: a short name and ONE sentence capturing the generative move (HOW the "
        "author reasons), phrased so it could apply to NEW problems the author never wrote about.\n"
        f"Output exactly {k} lines, each:\nKERNEL: <name> — <one-sentence generative method>\n\n"
        f"Passages:\n{passages}\n"
    )
    body = json.dumps({"model": KERNEL_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.4}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=420) as r:
        out = json.loads(r.read()).get("response", "")
    kernels = []
    for ln in out.splitlines():
        m = re.match(r"\s*KERNEL[:\-]\s*(.+)", ln, re.I)
        if m:
            kernels.append(m.group(1).strip())
    return kernels


def binom_z(wins, n):
    if n == 0:
        return 0.0, 0.5
    p = wins / n
    z = (p - 0.5) / math.sqrt(0.25 / n)
    return z, p


def main():
    slugs = sys.argv[1:] or list(AUTHORS)
    data = {}
    for slug in slugs:
        body = p1_body(slug)
        tr, hd = split(body)
        print(f"{slug}: P1-тело {len(body)} чанков → train {len(tr)} / held-out {len(hd)}")
        ks = extract_kernels(AUTHORS[slug], tr)
        print(f"  кернелы ({len(ks)}):")
        for x in ks:
            print(f"    • {x}")
        data[slug] = {"held": hd, "kernels": ks}

    # эмбеддинги
    for slug, d in data.items():
        d["kvec"] = embed(d["kernels"])
        d["hvec"] = embed([c["text"][:500] for c in d["held"]])

    print("\n=== ДИСКРИМИНАЦИЯ (own-win-rate: held-out ближе к СВОИМ кернелам, чем к чужим) ===")
    others = {s: [o for o in data if o != s] for s in data}
    for slug, d in data.items():
        if not others[slug]:
            print(f"{slug}: нет второго советника для кросс-теста"); continue
        oth = others[slug][0]
        wins = 0
        for hv in d["hvec"]:
            own = max(cos(hv, kv) for kv in d["kvec"])
            alt = max(cos(hv, kv) for kv in data[oth]["kvec"])
            wins += own > alt
        z, p = binom_z(wins, len(d["hvec"]))
        sig = "✓ значимо" if abs(z) > 1.96 else "✗ не значимо"
        print(f"{slug:16} own>{oth}: {wins}/{len(d['hvec'])} = {p:.1%}  z={z:+.2f}  {sig}")


if __name__ == "__main__":
    main()
