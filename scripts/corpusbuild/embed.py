"""Эмбеддинги (bge-m3 через ollama) и косинус. Косинус — чистый, юнит-тестируем без сети."""
import os, json, math, urllib.request

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")


def cosine(a, b) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def embed_texts(texts, batch: int = 64) -> list:
    """Возвращает НОРМИРОВАННЫЕ векторы для texts (bge-m3, многоязычный)."""
    out = []
    for i in range(0, len(texts), batch):
        body = json.dumps({"model": EMBED_MODEL, "input": texts[i:i + batch]}).encode()
        req = urllib.request.Request(f"{OLLAMA}/api/embed", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            out.extend(json.loads(r.read())["embeddings"])
    norm = []
    for v in out:
        s = math.sqrt(sum(x * x for x in v)) or 1.0
        norm.append([x / s for x in v])
    return norm
