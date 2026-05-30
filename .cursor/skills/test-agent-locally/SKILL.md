---
name: test-agent-locally
description: Run and test the AlphaSignal agent locally without Docker. Use when verifying a code change, debugging agent behavior, triggering a one-shot run, or inspecting LangSmith traces.
disable-model-invocation: true
---

# Test Agent Locally

## Prerequisites

```bash
# 1. Create and activate virtualenv (once)
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Create local data directory for SQLite
mkdir data

# 4. Copy and fill .env
cp .env.example .env
# Set OPENAI_API_KEY, TAVILY_API_KEY, SMTP_*, EMAIL_*
# Set DATABASE_URL=sqlite:///./data/ai_watch.db   (local path, not /data)
```

## One-shot run (no scheduler)

```bash
python -m backend.app.jobs.run_daily_alphasignal
```

Expected output:
- `status=processed` → email sent, publication stored in memory
- `status=skipped` → already seen, no email
- `status=error` → check logs for parse/network failure

## Run with scheduler + health API

```bash
RUN_ON_STARTUP=true python -m backend.app.jobs.scheduler
```

- Health: `http://localhost:8000/health` — shows next scheduled run time
- Manual trigger: `curl -X POST http://localhost:8000/run-now`

## Run tests (no network, all mocked)

```bash
pytest -q
```

All tests mock Tavily, OpenAI, LangSmith, and SMTP.

## Inspect SQLite memory

```bash
sqlite3 data/ai_watch.db "SELECT * FROM seen_publications ORDER BY seen_at DESC LIMIT 5;"
```

## Reset memory (force reprocess)

```bash
sqlite3 data/ai_watch.db "DELETE FROM seen_publications;"
```

## LangSmith traces

Set `LANGCHAIN_API_KEY` and `LANGCHAIN_TRACING_V2=true` in `.env`.
Traces appear in [smith.langchain.com](https://smith.langchain.com) under project `ai-watch-alphasignal`.

## Common issues

| Symptom | Likely cause |
|---------|-------------|
| No archive entries parsed | Tavily returned shell HTML — check raw Tavily response |
| `status=error` on archive fetch | Invalid `TAVILY_API_KEY` or AlphaSignal blocked the request |
| SMTP auth failure | Wrong `SMTP_USER`/`SMTP_PASSWORD` or app password needed (Gmail) |
| SQLite path error in Docker | Mount `./data:/data` and use `DATABASE_URL=sqlite:////data/ai_watch.db` |
