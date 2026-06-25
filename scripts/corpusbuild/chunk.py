"""Чанкинг (стратегия size). Граница тира РВЁТ чанк (не склеиваем B-интро с P1-телом).
Каждый чанк несёт tier. Config: {target, overlap}."""


def chunk_records(tagged, source: str, config=None):
    config = config or {}
    target = int(config.get("target", 900))
    overlap = int(config.get("overlap", 180))
    chunks = []
    buf, start_loc, last_loc, cur_tier, cur = [], None, None, None, 0

    def flush():
        nonlocal buf, start_loc, last_loc, cur
        body = " ".join(buf).strip()
        if body:
            chunks.append({"source": source, "tier": cur_tier,
                           "start": list(start_loc), "end": list(last_loc), "text": body})

    for rec in tagged:
        if cur_tier is not None and rec["tier"] != cur_tier:
            flush(); buf, start_loc, cur = [], None, 0      # граница тира
        cur_tier = rec["tier"]
        if start_loc is None:
            start_loc = rec["loc"]
        buf.append(rec["text"]); last_loc = rec["loc"]; cur += len(rec["text"]) + 1
        if cur >= target:
            flush()
            tail, tlen = [], 0
            for t in reversed(buf):
                tail.insert(0, t); tlen += len(t) + 1
                if tlen >= overlap:
                    break
            buf = tail; start_loc = last_loc; cur = sum(len(t) + 1 for t in buf)
    if buf:
        flush()
    return chunks
