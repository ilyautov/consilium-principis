"""SemanticEngine — обёртка существующего tier_full.py (ollama bge-m3 + Гефест) под
контракт Engine. Логику ретрива НЕ дублирует. Гибридный ретрив — отдельная фаза (Task 9).
tier_full лежит в scripts/ (на уровень выше пакета engine) → импортится top-level."""
from typing import List

from . import Engine, Passage   # relative — пакетный стиль


class SemanticEngine(Engine):
    name = "semantic"
    DEFAULT_THRESHOLD = 0.50  # калиброван на реальном корпусе при chunk_chars=500

    @staticmethod
    def available() -> bool:
        try:
            import tier_full
            return bool(tier_full.available())
        except Exception:
            return False

    def retrieve(self, question, advisor_dir, top_k=3):
        import tier_full
        raw = tier_full.retrieve(question, advisor_dir, top_k=top_k)
        return [Passage(text=d["text"], score=float(d["score"]), source=d["source"]) for d in raw]

    def build_index(self, advisor_dir):
        import tier_full, os
        tier_full.build_index(advisor_dir)
        return {"chunk_chars": int(os.getenv("TIER_CHUNK_CHARS", "500"))}

    def abstain_threshold(self, advisor_dir):
        from . import load_backend_threshold
        return load_backend_threshold(advisor_dir, self.name, self.DEFAULT_THRESHOLD)
