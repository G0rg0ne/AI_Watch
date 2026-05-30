# AI Watch - AlphaSignal News Agent

Daily AI/ML news agent that monitors the [AlphaSignal archive](https://alphasignal.ai/archive), detects new newsletter publications, extracts headlines and summaries, generates an OpenAI digest, and emails it via SMTP only when a new publication is found.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.11 |
| API / Health | FastAPI + Uvicorn |
| Scheduler | APScheduler (internal daily cron) |
| Web retrieval | httpx (AlphaSignal JSON APIs) |
| Summarization | OpenAI |
| Observability | LangSmith |
| Memory | SQLite (persistent dedup) |
| Email | Generic SMTP |
| Packaging | Docker |

## Project Structure

```
AI_Watch/
├── backend/
│   ├── app/
│   │   ├── core/config.py          # Environment settings
│   │   ├── db/database.py            # SQLite engine
│   │   ├── models/seen_publication.py
│   │   ├── services/alphasignal/   # Agent services
│   │   ├── jobs/                   # Scheduler + daily job
│   │   └── main.py                 # Health API
│   └── requirements.txt
├── shared/schemas/alphasignal.py   # Shared Pydantic models
├── tests/backend/                  # Unit tests
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
└── DEVELOPMENT.md
```

## How It Works

1. **Daily scheduler** triggers the agent at the configured UTC time.
2. **httpx** fetches the AlphaSignal archive JSON API.
3. **Archive parser** extracts publication title, URL, and datetime from each row.
4. **Memory (SQLite)** checks whether the newest publication was already processed.
5. If new, **httpx** fetches the newsletter JSON API (`/api/archive/{campaign_id}`) and unwraps embedded HTML.
6. **Newsletter parser** extracts highlight titles, detailed summaries/resumes, and detail links.
7. **LangSmith** supplies the summarization chat prompt; **OpenAI** generates an email-ready digest.
8. **SMTP** sends the email and the publication is stored in memory.

Emails are **not** sent when the latest publication was already seen.

## Setup

### 1. Clone and configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and SMTP credentials
```

### 2. Local development (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt
```

Create a local data directory for SQLite:

```bash
mkdir data
```

Set `DATABASE_URL=sqlite:///./data/ai_watch.db` in `.env` for local runs (Docker uses `/data`).

Run once manually:

```bash
python -m backend.app.jobs.run_daily_alphasignal
```

Run with scheduler + health API:

```bash
python -m backend.app.jobs.scheduler
```

### 3. Docker (recommended)

```bash
docker compose up --build
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)

Manual trigger (testing):

```bash
curl -X POST http://localhost:8000/run-now
```

### 4. Push to Docker Hub

```bash
docker build -t YOUR_DOCKERHUB_USER/ai-watch:latest .
docker push YOUR_DOCKERHUB_USER/ai-watch:latest
```

Deploy the image with `.env` secrets injected at runtime and a persistent volume mounted at `/data`.

## LangSmith summarizer prompt

The newsletter summarization **system + user prompt** is stored in [LangSmith Prompt Hub](https://smith.langchain.com/), not in code. Set `LANGSMITH_SUMMARIZER_PROMPT` to the prompt name or `name:tag` (for example `alphasignal-newsletter-summarizer:prod`).

### Create the prompt (UI or SDK)

1. In LangSmith, open **Prompts** → **New prompt**.
2. Use a **chat** prompt named `alphasignal-newsletter-summarizer` with:
   - **System**: analyst instructions (executive summary, highlights, detailed section, plain-text email tone).
   - **User**: `Summarize this AlphaSignal newsletter for email delivery.\n\n{newsletter_payload}`
3. Tag a stable version as `prod` if you want pinned production behavior.

One-time push via Python:

```python
from langchain_core.prompts import ChatPromptTemplate
from langsmith import Client

client = Client()
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an AI/ML news analyst. Summarize AlphaSignal newsletter content clearly and concisely.
Produce:
1. A short executive summary (3-5 sentences)
2. Highlight section with bullet points for top headlines
3. Detailed section with bullet points including each item's resume/summary and its detail link when available
Keep the tone professional and informative. Use plain text suitable for email."""),
    ("user", "Summarize this AlphaSignal newsletter for email delivery.\n\n{newsletter_payload}"),
])
client.push_prompt("alphasignal-newsletter-summarizer", object=prompt)
```

`LANGCHAIN_API_KEY` must be set so the agent can `pull_prompt` at runtime.

## LangSmith tracing

The top-level `alphasignal_agent_run` trace includes a `trigger` input so runs are easier to identify:

| Trigger | Source |
|---------|--------|
| `cli` | `python -m backend.app.jobs.run_daily_alphasignal` |
| `scheduler` | Daily APScheduler cron job |
| `startup` | Immediate run when `RUN_ON_STARTUP=true` |
| `manual_api` | `POST /run-now` |
| `direct` | Direct `AlphaSignalAgent.run()` or `run_alphasignal_agent()` call without an explicit trigger |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `LANGCHAIN_TRACING_V2` | No | Enable LangSmith tracing (default: `true`) |
| `LANGCHAIN_API_KEY` | No | LangSmith API key |
| `LANGCHAIN_PROJECT` | No | LangSmith project name |
| `LANGCHAIN_ENDPOINT` | No | LangSmith endpoint |
| `LANGSMITH_SUMMARIZER_PROMPT` | No | LangSmith Prompt Hub id for summarizer (default: `alphasignal-newsletter-summarizer:prod`) |
| `ALPHASIGNAL_BASE_URL` | No | AlphaSignal site origin (default: `https://alphasignal.ai`) |
| `ALPHASIGNAL_ARCHIVE_URL` | No | Public archive page URL (reference only) |
| `ALPHASIGNAL_ARCHIVE_API_URL` | No | Archive listing API URL (default: `https://alphasignal.ai/api/archive?page=1&limit=10`) |
| `DATABASE_URL` | No | SQLite URL (default: `/data/ai_watch.db` in Docker) |
| `SMTP_HOST` | Yes | SMTP server host |
| `SMTP_PORT` | No | SMTP port (default: `587`) |
| `SMTP_USER` | Yes | SMTP username |
| `SMTP_PASSWORD` | Yes | SMTP password |
| `SMTP_USE_TLS` | No | Use STARTTLS (default: `true`) |
| `EMAIL_FROM` | Yes | Sender email address |
| `EMAIL_TO` | Yes | Recipient email address |
| `RUN_HOUR_UTC` | No | Daily run hour UTC (default: `8`) |
| `RUN_MINUTE_UTC` | No | Daily run minute UTC (default: `0`) |
| `RUN_ON_STARTUP` | No | Run immediately on container start (default: `false`) |
| `APP_HOST` | No | Health API host (default: `0.0.0.0`) |
| `APP_PORT` | No | Health API port (default: `8000`) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check and next scheduled run |
| `POST` | `/run-now` | Manually trigger one agent run |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Testing

```bash
pip install -r backend/requirements.txt
pytest
```

Tests cover archive parsing, newsletter parsing, summarizer OpenAI calls, memory deduplication, and agent skip/process flows (mocked AlphaSignal client, OpenAI, SMTP).

## Deployment Notes

- Mount a persistent volume at `/data` so publication memory survives restarts.
- Inject secrets via environment variables or a secrets manager; never bake them into the image.
- LangSmith traces are available when `LANGCHAIN_API_KEY` is set.
- Summarization prompts are pulled from LangSmith at runtime; create the prompt in Prompt Hub before the first successful digest run.
- OpenAI calls use LangSmith's `wrap_openai` client wrapper so Monitoring shows **model name** and **token usage** (prompt/completion/total) on LLM runs. Pipeline steps still use `@traceable_step`; only runs that call OpenAI (non-skipped) appear in usage charts.
- Set `RUN_ON_STARTUP=true` if you want an immediate run when the container starts.

## Recent Changes

See [DEVELOPMENT.md](DEVELOPMENT.md) for the development log and changelog.
