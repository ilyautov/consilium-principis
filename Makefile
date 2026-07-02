# Consilium-Principis — dev-ритуалы

.PHONY: test moat-check moat-baseline

# Оффлайн-сьют (без ollama/движка — CI-инвариант)
test:
	HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q

# §3.3: pre-release ритуал рва — фиксированная батарея против docs/dev/moat-baseline.json.
# Требует: ollama (bge-m3 для ретрива) + судья (OPENROUTER_API_KEY в env/./.env, дефолт
# gemini-2.5-flash; фоллбэк --judge ollama). Exit ≠ 0 при деградации сверх допусков.
moat-check:
	python3 scripts/moat_check.py --baseline docs/dev/moat-baseline.json

# Перезапись базлайна (осознанное действие после принятых изменений рва)
moat-baseline:
	python3 scripts/moat_check.py --baseline docs/dev/moat-baseline.json --write-baseline
