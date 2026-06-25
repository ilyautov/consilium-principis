"""Калиброванный enrichment: LLM-расшифровка P1 в примеры/ситуации/кросс-домен/осовременивание.
Всегда derived+never_quote, trace к источнику. L2.3.2: кросс-домен обязан трассироваться к кернелу.
make_enrichment_record — чистая, юнит-гейт инвариантов."""
import json
from . import ids, paths

# ВНИМАНИЕ: "кросс-домен" требует traces_to_kernel (L2.3.2) → генерится ОТДЕЛЬНЫМ проходом с
# привязкой к кернелу, НЕ через build_enrichment (его дефолт — пример/ситуация). Не вызывать
# build_enrichment(kinds=["кросс-домен"]) без kernel-trace — make_enrichment_record бросит ValueError.
KINDS = ["пример", "ситуация", "кросс-домен", "осовременивание"]


def make_enrichment_record(kind: str, text: str, derived_from: list, traces_to_kernel: str = None) -> dict:
    if kind == "кросс-домен" and not traces_to_kernel:
        raise ValueError("кросс-домен обязан трассироваться к кернелу (L2.3.2)")
    rec = {"kind": kind, "text": text, "derived_from": list(derived_from),
           "tier": "derived", "never_quote": True}
    if traces_to_kernel:
        rec["traces_to_kernel"] = traces_to_kernel
    return rec


def _generate(text: str, kind: str) -> str:
    """LLM-расшифровка одного P1-пассажа в один enrichment-текст (gemma)."""
    import os, urllib.request
    ollama = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.getenv("KERNEL_MODEL", "gemma3:27b")
    prompt = (f"Пассаж первоисточника:\n{text[:800]}\n\n"
              f"Дай ОДНО краткое «{kind}» (1-3 предложения), раскрывающее идею пассажа для современного "
              f"читателя. Не цитируй дословно — это производный текст.")
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.5}}).encode()
    req = urllib.request.Request(f"{ollama}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=420) as r:
        return json.loads(r.read()).get("response", "").strip()


def build_enrichment(advisor_dir: str, kinds=None, limit: int = 60) -> list:
    """Генерит enrichment для сэмпла P1-пассажей. kinds=пример/ситуация по умолчанию (кросс-домен —
    отдельным проходом с привязкой к кернелу, см. exp; здесь базовые)."""
    kinds = kinds or ["пример", "ситуация"]
    corpus = ids.load_corpus(advisor_dir)
    p1c = [c for c in corpus if c["tier"] in ("P1", "P2") and len(c.get("text", "")) > 300]
    step = max(1, len(p1c) // limit)
    sample = p1c[::step][:limit]
    out_recs = []
    for c in sample:
        for kind in kinds:
            txt = _generate(c["text"], kind)
            if txt:
                out_recs.append(make_enrichment_record(kind, txt, derived_from=[c["id"]]))
    out = f"{paths.build_dir(advisor_dir)}/enrichment.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in out_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[enrich] {advisor_dir}: {len(out_recs)} derived-записей → {out}")
    return out_recs
