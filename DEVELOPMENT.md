# Development Log

## [2026-05-30 23:40] - FEATURE

### Changes
- Added a `trigger` input to `AlphaSignalAgent.run()` so the top-level LangSmith trace shows why a run started
- Propagated explicit trigger labels from CLI (`cli`), APScheduler (`scheduler`), startup runs (`startup`), and the manual API endpoint (`manual_api`)
- Added a focused test for trigger propagation through `run_alphasignal_agent()`
- Documented LangSmith trace trigger labels in the README

### Files Modified
- `backend/app/services/alphasignal/agent.py`
- `backend/app/jobs/run_daily_alphasignal.py`
- `backend/app/jobs/scheduler.py`
- `backend/app/main.py`
- `tests/backend/test_alphasignal_memory.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
LangSmith showed an empty input section for `alphasignal_agent_run` because the traced method had no business arguments. Passing a small trigger label makes traces clearer without exposing secrets or large newsletter payloads.

### Breaking Changes
None

### Next Steps
- Trigger one run from each entrypoint and confirm the LangSmith `Input` panel shows the expected `trigger` value

## [2026-05-30 23:15] - FEATURE

### Changes
- Moved AlphaSignal summarizer system/user prompts from hardcoded `SYSTEM_PROMPT` to LangSmith Prompt Hub
- Added `langsmith_summarizer_prompt` setting (`LANGSMITH_SUMMARIZER_PROMPT`, default `alphasignal-newsletter-summarizer:prod`)
- `NewsletterSummarizer` pulls a `ChatPromptTemplate` via `langsmith.Client.pull_prompt`, formats `{newsletter_payload}`, and converts messages for OpenAI
- Added `langchain-core` dependency for LangSmith prompt deserialization
- Restored `.env.example` with placeholder secrets and new LangSmith prompt variable
- Extended summarizer tests to mock LangSmith client and verify prompt id + message formatting

### Files Modified
- `backend/app/core/config.py`
- `backend/app/services/alphasignal/summarizer.py`
- `backend/requirements.txt`
- `tests/backend/test_summarizer.py`
- `.env.example`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
User requested managing the summarization prompt in LangSmith and loading it at runtime so prompt edits do not require code deploys.

### Breaking Changes
- Requires `LANGCHAIN_API_KEY` and an existing LangSmith prompt matching `LANGSMITH_SUMMARIZER_PROMPT` before summarization succeeds (no in-code fallback).

### Next Steps
- Push `alphasignal-newsletter-summarizer` to LangSmith and tag `prod` (or adjust env to match your prompt name)
- Run agent once to verify `pull_prompt` and OpenAI summary in LangSmith traces

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

## [2026-05-30 20:35] - BUGFIX

### Changes
- Switched archive retrieval from the client-rendered `/archive` page to AlphaSignal's JSON API (`/api/archive`)
- Added JSON archive parsing with `/email/{campaign_id}` canonical publication URLs
- Resolved newsletter fetches to `/api/archive/{campaign_id}` and unwrap embedded newsletter HTML from API JSON
- Added `ALPHASIGNAL_BASE_URL` and `ALPHASIGNAL_ARCHIVE_API_URL` settings plus `.env.example`

### Files Modified
- `backend/app/services/alphasignal/archive_parser.py`
- `backend/app/services/alphasignal/tavily_client.py`
- `backend/app/services/alphasignal/agent.py`
- `backend/app/core/config.py`
- `tests/backend/test_archive_parser.py`
- `tests/backend/test_alphasignal_memory.py`
- `.env.example`
- `README.md`

### Rationale
Tavily extract returned zero results for the AlphaSignal archive HTML page because it is a JavaScript SPA shell. The public JSON API returns structured publication metadata that Tavily can extract reliably.

### Breaking Changes
None for existing SQLite memory; publication URLs now use `/email/{campaign_id}` instead of legacy `/newsletter/{slug}` paths for newly parsed entries.

### Next Steps
- Rebuild and restart Docker (`docker compose up --build`) to pick up the fix

## [2026-05-30 20:45] - BUGFIX

### Changes
- Fetch AlphaSignal archive and newsletter JSON via direct `httpx` calls instead of Tavily extract
- Added `sanitize_tavily_json()` to undo Tavily markdown escaping (`\_`) when JSON payloads are parsed
- Updated agent tests to mock `fetch_archive_listing()` and `fetch_newsletter_content()`
- Promoted `httpx` from test-only to runtime dependency

### Files Modified
- `backend/app/services/alphasignal/tavily_client.py`
- `backend/app/services/alphasignal/agent.py`
- `backend/app/services/alphasignal/archive_parser.py`
- `backend/requirements.txt`
- `tests/backend/test_alphasignal_memory.py`
- `README.md`

### Rationale
Tavily extract returned JSON with invalid markdown escapes (e.g. `total\_records`), causing `json.loads` to fail and the archive parser to report zero entries even after switching to the API URL.

### Breaking Changes
None

### Next Steps
- Rebuild Docker and confirm `Parsed 10 archive entries from API JSON` in logs

## [2026-05-30 22:55] - BUGFIX

### Changes
- Wrapped the OpenAI SDK client with LangSmith `wrap_openai` in `NewsletterSummarizer` so LLM runs record model and token usage in LangSmith Monitoring
- Added unit tests for client wrapping, configured model passthrough, and empty-response handling

### Files Modified
- `backend/app/services/alphasignal/summarizer.py`
- `tests/backend/test_summarizer.py`
- `README.md`

### Rationale
Generic `@traceable` steps logged pipeline activity but not LLM usage metadata; LangSmith Monitoring requires provider-instrumented OpenAI calls to populate token and model metrics.

### Breaking Changes
None

### Next Steps
- Trigger a non-skipped agent run and confirm the LangSmith trace shows an LLM child run with `usage_metadata` and `OPENAI_MODEL`
