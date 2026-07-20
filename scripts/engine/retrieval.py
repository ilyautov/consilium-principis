"""retrieval.py — ПРОД-путь retrieve поверх Engine-контракта (M11: вынесен из eval.py).

Единая точка ретрива для cite/retrieve (mcp_server._retrieve/_cite): resolve_engine →
Engine.retrieve → MCP-форма dict {text, score, source, tier[, raw_score]}; при падении
бэкенда — наблюдаемая (stderr) деградация на лексический пол (char-3gram Jaccard по
предложениям корпуса, tier=SIMPLE).

EVAL_ENGINE здесь НЕ читается (ревью 4.3, Important): env-форс бэкенда — забота ТОЛЬКО
eval-CLI (eval.py обёртка прокидывает его ЯВНЫМ prefer=). Прод-путь зовёт retrieve без
prefer → auto-резолюция движка.
"""
import os
import re
import json
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from corpusbuild.paths import corpus_path


def norm(s):
    # ё→е держим в синхроне с engine/fidelity._norm — иначе прод-ретрив и гейт нормализуют
    # по-разному (ревью 2026-07-20, Minor).
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.U)
    return re.sub(r"\s+", " ", s).strip()


def split_corpus_units(adv_dir):
    """Корпус → [(предложение, tier)] кандидатов для ретрива. Один чанк corpus.jsonl бьём по
    предложениям, чтобы top-1/top-3 имели нетривиальный выбор (иначе ретрив бессмыслен на
    1 чанке). Тир едет с текстом — контракт Passage/retrieve его отдаёт; нет поля → None."""
    cj = corpus_path(adv_dir)
    if not os.path.isfile(cj):
        return []
    units = []
    for line in open(cj, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        txt = rec.get("text", "")
        tier = rec.get("tier")
        for sent in re.split(r"(?<=[.!?])\s+", txt):
            sent = sent.strip()
            if len(sent) >= 8:
                units.append((sent, tier))
    return units


def _char_ngrams(s, n=3):
    s = norm(s)
    s = "  " + s + "  "
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def lexical_retrieve(question, adv_dir, top_k=3):
    """Fallback-ретрив (tier=SIMPLE): char-3gram Jaccard юзер-вопроса против юнитов корпуса.
    Возвращает контракт Engine.retrieve в dict-форме: [{text, score, source, tier}],
    score∈[0,1] по убыванию."""
    units = split_corpus_units(adv_dir)
    if not units:
        return []
    qg = _char_ngrams(question)
    if not qg:
        return []
    scored = []
    for u, tier in units:
        ug = _char_ngrams(u)
        inter = len(qg & ug)
        union = len(qg | ug) or 1
        scored.append({"text": u, "score": inter / union, "source": "corpus.jsonl",
                       "tier": tier})
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:top_k]


def retrieve(question, adv_dir, top_k=3, prefer=None):
    """Единая точка: через Engine-контракт (resolve_engine), с graceful-деградацией.
    Fallback на лексический пол при ПАДЕНИИ бэкенда. prefer='lexical'|'semantic'|'hybrid'
    форсит бэкенд явно (eval-CLI); None (дефолт, прод-путь) → auto-резолюция."""
    from . import resolve_engine   # lazy (идиом lexical.py): тесты патчат engine.resolve_engine
    eng = resolve_engine(adv_dir, prefer=prefer)
    try:
        out = []
        for p in eng.retrieve(question, adv_dir, top_k=top_k):
            d = {"text": p.text, "score": p.score, "source": p.source, "tier": p.tier}
            # M4: сырой косинус поверх hybrid_alpha-смеси/RRF — гейт релевантности
            # режет полосой ЕГО, не смесь. Нет raw (чистая семантика/lexical) — ключа нет.
            if getattr(p, "raw_score", None) is not None:
                d["raw_score"] = p.raw_score
            out.append(d)
        return out
    except Exception as e:
        # НЕ молча: деградация семантики до лексич. пола наблюдаема (иначе FULL «как бы есть»,
        # а recall тихо рухнул). Гейт верности при этом не страдает — но качество да.
        print(f"[retrieve] {type(eng).__name__} упал ({e}); деградация → лексический пол",
              file=_sys.stderr)
    return lexical_retrieve(question, adv_dir, top_k=top_k)
