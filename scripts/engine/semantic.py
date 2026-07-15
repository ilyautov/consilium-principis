"""SemanticEngine — обёртка существующего tier_full.py (ollama bge-m3 + Гефест) под
контракт Engine. Логику ретрива НЕ дублирует. Гибридный ретрив — отдельная фаза (Task 9).
tier_full лежит в scripts/ (на уровень выше пакета engine) → импортится top-level."""
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
        import os, re, tier_full
        from . import load_config_value
        pool = max(top_k, int(os.getenv("HYBRID_POOL", "10")))
        raw = tier_full.retrieve(question, advisor_dir, top_k=pool)
        # alpha: env override (эксперимент) → board_config hybrid_alpha → 0.0 (чистая семантика).
        env_alpha = os.getenv("HYBRID_ALPHA")
        alpha = float(env_alpha) if env_alpha is not None else float(load_config_value("hybrid_alpha", 0.0))
        if alpha <= 0:
            return [Passage(d["text"], float(d["score"]), d["source"], d.get("tier"))
                    for d in raw[:top_k]]

        def toks(s):
            return set(re.sub(r"[^\w\s]", " ", s.lower()).split())
        qt = toks(question)
        rescored = []
        for d in raw:
            dt = toks(d["text"])
            lex = len(qt & dt) / (len(qt) or 1)
            score = (1 - alpha) * float(d["score"]) + alpha * lex
            rescored.append(Passage(d["text"], score, d["source"], d.get("tier")))
        rescored.sort(key=lambda p: p.score, reverse=True)
        return rescored[:top_k]

    def build_index(self, advisor_dir):
        import tier_full, os
        tier_full.build_index(advisor_dir)
        return {"chunk_chars": int(os.getenv("TIER_CHUNK_CHARS", "500"))}

    def abstain_threshold(self, advisor_dir):
        from . import load_backend_threshold
        return load_backend_threshold(advisor_dir, self.name, self.DEFAULT_THRESHOLD)
