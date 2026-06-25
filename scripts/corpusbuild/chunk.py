"""Чанкинг (стратегия size). Граница тира РВЁТ чанк (не склеиваем B-интро с P1-телом).
Каждый чанк несёт tier. Config: {target, overlap}."""


def chunk_records(tagged, source: str, config=None):
    config = config or {}
    target = int(config.get("target", 900))
    overlap = int(config.get("overlap", 180))
    chunks = []
    buf, cur_tier, cur = [], None, 0   # buf = [(text, loc), ...] — loc держим рядом с текстом,
    #                                    чтобы overlap-хвост сохранял ВЕРНУЮ стартовую позицию

    def flush():
        body = " ".join(t for t, _ in buf).strip()
        if body and buf:
            chunks.append({"source": source, "tier": cur_tier,
                           "start": list(buf[0][1]), "end": list(buf[-1][1]), "text": body})

    for rec in tagged:
        if cur_tier is not None and rec["tier"] != cur_tier:
            flush(); buf, cur = [], 0      # граница тира
        cur_tier = rec["tier"]
        buf.append((rec["text"], rec["loc"])); cur += len(rec["text"]) + 1
        if cur >= target:
            flush()
            tail, tlen = [], 0
            for item in reversed(buf):
                tail.insert(0, item); tlen += len(item[0]) + 1
                if tlen >= overlap:
                    break
            buf = tail; cur = sum(len(t) + 1 for t, _ in buf)
    if buf:
        flush()
    return chunks
