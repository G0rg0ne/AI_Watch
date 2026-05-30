# Development Log

## [2026-05-30 22:30] - CONFIG

### Changes
- Added four Cursor rules for persistent AI guidance across sessions
- Added two project-level Cursor skills for common development workflows

### Files Modified
- `.cursor/rules/project-context.mdc` — always-on project overview and architecture
- `.cursor/rules/python-agent-standards.mdc` — Python coding standards (applies to `**/*.py`)
- `.cursor/rules/backend-services.mdc` — service layer patterns (applies to `backend/app/services/**/*.py`)
- `.cursor/rules/documentation-workflow.mdc` — mandatory doc update checklist (always-on)
- `.cursor/skills/add-agent-service/SKILL.md` — how to extend the agent with a new service
- `.cursor/skills/test-agent-locally/SKILL.md` — how to run and debug the agent locally

### Rationale
Keeps every future AI session aware of the project architecture, coding conventions, and documentation obligations without requiring the user to re-explain context. Skills codify the two most common developer workflows.

### Breaking Changes
None

### Next Steps
- Validate parsers against live AlphaSignal content once API keys are configured
- Push image to Docker Hub

## [2026-05-30 22:15] - FEATURE

### Changes
- Implemented greenfield AlphaSignal news agent with daily internal scheduler
- Added Tavily-based archive and newsletter retrieval
- Added archive parser for publication title, URL, and datetime deduplication
- Added newsletter parser for highlight titles, detailed summaries/resumes, and detail links
- Added SQLite persistent memory to skip already-processed publications
- Added OpenAI summarization and SMTP email delivery
- Added LangSmith tracing hooks for observability
- Added Docker image, docker-compose, health API, and environment configuration
- Added unit tests for parsers, memory, and agent workflow

### Files Modified
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/db/database.py`
- `backend/app/models/seen_publication.py`
- `backend/app/jobs/scheduler.py`
- `backend/app/jobs/run_daily_alphasignal.py`
- `backend/app/services/tracing.py`
- `backend/app/services/alphasignal/tavily_client.py`
- `backend/app/services/alphasignal/archive_parser.py`
- `backend/app/services/alphasignal/newsletter_parser.py`
- `backend/app/services/alphasignal/memory.py`
- `backend/app/services/alphasignal/summarizer.py`
- `backend/app/services/alphasignal/email_sender.py`
- `backend/app/services/alphasignal/agent.py`
- `shared/schemas/alphasignal.py`
- `backend/requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `.gitignore`
- `pytest.ini`
- `tests/conftest.py`
- `tests/backend/test_archive_parser.py`
- `tests/backend/test_newsletter_parser.py`
- `tests/backend/test_alphasignal_memory.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
User requested a self-contained Docker-deployable agent that scans AlphaSignal daily, uses Tavily for web retrieval, OpenAI for summaries, LangSmith for tracing, SMTP for email alerts, and persistent memory to email only on new publications.

### Breaking Changes
None (initial implementation)

### Next Steps
- Validate parsers against live AlphaSignal HTML if Tavily output differs from fixtures
- Add optional Streamlit dashboard for run history
- Add retry/backoff for transient Tavily or SMTP failures
- Push image to Docker Hub and configure production secrets/volume
