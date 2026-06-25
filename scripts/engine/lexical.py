"""LexicalEngine — 0-install пол (tier SIMPLE). char-3gram Jaccard вопроса против
предложений корпуса. Никаких внешних зависимостей (stdlib). Порог abstain низкий и
лексический — на кросс-язычных вопросах abstention тут best-effort; жёсткая гарантия —
fidelity (наследуется из базового Engine)."""
import os
import re
import json
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from corpusbuild.paths import corpus_path
from typing import List

from . import Engine, Passage   # relative — пакетный стиль


# intentional copy of _norm (floor isolation: lexical depends on stdlib only, not on fidelity/eval)
def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _char_ngrams(s: str, n: int = 3):
    s = "  " + _norm(s) + "  "
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _split_units(advisor_dir: str) -> List[str]:
    cj = corpus_path(advisor_dir)
    if not os.path.isfile(cj):
        return []
    units = []
    with open(cj, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                txt = json.loads(line).get("text") or ""
            except Exception:
                continue
            for sent in re.split(r"(?<=[.!?])\s+", txt):
                sent = sent.strip()
                if len(sent) >= 8:
                    units.append(sent)
    return units


class LexicalEngine(Engine):
    name = "lexical"
    DEFAULT_THRESHOLD = 0.04  # jaccard-скоры малы; калибруется в board_config

    def retrieve(self, question, advisor_dir, top_k=3):
        units = _split_units(advisor_dir)
        if not units or not _norm(question):
            return []
        qg = _char_ngrams(question)
        scored = []
        for u in units:
            ug = _char_ngrams(u)
            union = len(qg | ug) or 1
            scored.append(Passage(text=u, score=len(qg & ug) / union, source="corpus.jsonl"))
        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[:top_k]

    def build_index(self, advisor_dir):
        return {}  # лексике индекс не нужен

    def abstain_threshold(self, advisor_dir):
        from . import load_backend_threshold
        return load_backend_threshold(advisor_dir, self.name, self.DEFAULT_THRESHOLD)
