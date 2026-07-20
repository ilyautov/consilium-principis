"""HybridEngine — Левер 1: настоящий union semantic ∪ lexical через RRF.

Зачем, а не alpha-rescoring в SemanticEngine: тот пере-взвешивает лишь семантический пул и
НЕ может поднять пассаж, который семантика вообще не достала. Диагностика (2026-06-25) показала,
что промахи — именно такие. RRF над ДВУМЯ независимыми выдачами их вытаскивает: лексика ловит
характерные фразы («armed prophets», «neutral path»), которые семантика хоронит, и наоборот.

Кросс-язык: семантика (bge-m3) робастна к языку → запрос как есть. Лексике (char-ngram) нужен
язык корпуса → query_lex (переведённый запрос, его даёт LLM-слой скилла). Если query_lex нет —
лексика берёт исходный запрос (мягкая деградация: для одноязычных пар работает, для кросс-язычных
вклад лексики ≈0, но семантика несёт).

Честность: abstain остаётся на КАЛИБРОВАННОМ семантическом score (порог 0.50), а не на RRF-шкале —
гейт молчания не должен сбиться из-за смены метрики.
"""
import os
from . import Engine, Passage


class HybridEngine(Engine):
    name = "hybrid"

    def __init__(self):
        from .semantic import SemanticEngine
        from .lexical import LexicalEngine
        self.sem = SemanticEngine()
        self.lex = LexicalEngine()

    def retrieve(self, question, advisor_dir, top_k=3, query_lex=None):
        from .rrf import rrf_fuse, _key
        pool = max(top_k, int(os.getenv("HYBRID_POOL", "20")))
        sem = self.sem.retrieve(question, advisor_dir, top_k=pool)
        lex = self.lex.retrieve(query_lex or question, advisor_dir, top_k=pool)
        fused = rrf_fuse([sem, lex], k=int(os.getenv("RRF_K", "60")), top_k=top_k)
        # M4: RRF-score — не косинус; сырой косинус semantic-ноги прокидываем в raw_score,
        # чтобы гейт релевантности (калиброван под косинус) не резал полосой слитый скор.
        # Если сама semantic-нога со смесью (hybrid_alpha>0) — берём её raw (pre-blend).
        # У lexical-only пассажей косинуса нет → raw_score остаётся None (гейт судит явно).
        cos_by_key = {}
        for p in sem:
            cos = p.raw_score if isinstance(p.raw_score, (int, float)) else p.score
            cos_by_key.setdefault(_key(p.text), cos)
        for p in fused:
            cos = cos_by_key.get(_key(p.text))
            if cos is not None:
                p.raw_score = cos
        return fused

    def build_index(self, advisor_dir):
        return self.sem.build_index(advisor_dir)

    def abstain_threshold(self, advisor_dir):
        return self.sem.abstain_threshold(advisor_dir)

    def abstain_check(self, question, advisor_dir):
        # гейт молчания — на калиброванной семантической шкале, не на RRF
        return self.sem.abstain_check(question, advisor_dir)
