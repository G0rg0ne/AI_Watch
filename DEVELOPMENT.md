# Development Log

## [2026-05-31 23:45] - CONFIG

### Changes
- Added a GitHub Actions workflow to build the self-contained Docker image from the root `Dockerfile`
- Configured Docker Hub login with repository secrets and tag-only publishing, using the Git tag as the Docker image tag
- Documented the required Docker Hub secrets and optional repository variable in the README

### Files Modified
- `.github/workflows/publish-docker-image.yml`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Automating Docker Hub publishing removes the manual image build/push step and makes production deployments reproducible from GitHub Actions.

### Breaking Changes
None

### Next Steps
- Add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` in GitHub repository secrets before pushing a release tag
- Optionally set `DOCKERHUB_REPOSITORY` if the Docker Hub repository should not be named `ai-watch`

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

## [2026-05-30 23:15] - REFACTOR

### Changes
- Removed Tavily dependency and `TAVILY_API_KEY` configuration
- Replaced `AlphaSignalTavilyClient` / `tavily_client.py` with `AlphaSignalClient` / `alphasignal_client.py` (direct `httpx` only)
- Renamed `sanitize_tavily_json()` to `sanitize_json_payload()` in archive parser
- Updated agent constructor injection from `tavily_client` to `alphasignal_client`
- Newsletter fetch now requires a resolvable `/email/{campaign_id}` URL; raises `ValueError` otherwise
- Updated tests, README, `.env.example`, and cursor rules to reflect direct API retrieval

### Files Modified
- `backend/app/services/alphasignal/alphasignal_client.py` (new)
- `backend/app/services/alphasignal/tavily_client.py` (removed)
- `backend/app/services/alphasignal/agent.py`
- `backend/app/services/alphasignal/archive_parser.py`
- `backend/app/services/alphasignal/newsletter_parser.py`
- `backend/app/core/config.py`
- `backend/requirements.txt`
- `tests/conftest.py`
- `tests/backend/test_summarizer.py`
- `tests/backend/test_alphasignal_memory.py`
- `.env.example`
- `README.md`
- `.cursor/rules/project-context.mdc`
- `.cursor/rules/backend-services.mdc`
- `.cursor/rules/python-agent-standards.mdc`

### Rationale
The daily agent path already used AlphaSignal JSON APIs via `httpx`; Tavily was unused fallback code, an extra paid dependency, and misleading naming/documentation.

### Breaking Changes
- `TAVILY_API_KEY` is no longer read; remove it from `.env` and deployment secrets.
- Code injecting `tavily_client=` must use `alphasignal_client=` instead.

### Next Steps
- Remove `TAVILY_API_KEY` from local `.env` and any deployment secret stores
- Rebuild Docker image after `pip install` without `tavily-python`

## [2026-05-31 23:45] - FEATURE

### Changes
- Added `ALPHASIGNAL_START_DATE` and `ALPHASIGNAL_ARCHIVE_LIMIT` settings for optional backfill cutoff and archive pagination page size
- Extended `AlphaSignalClient.fetch_archive_listing()` to paginate archive API pages when a start date is configured
- Added `PublicationMemory.find_unseen_since()` to return all eligible unseen editions oldest-first
- Refactored `AlphaSignalAgent.run()` to process every eligible unseen newsletter per run with partial-failure tolerance
- Extended `RunResult` with batch fields (`processed_count`, `publication_urls`, `email_sent_count`, failure counts/URLs) while keeping existing single-edition fields
- Added/updated unit tests for memory filtering, multi-edition runs, start-date cutoff, mixed seen/unseen, and partial failure
- Updated README and created `.env.example` with the new environment variables

### Files Modified
- `backend/app/core/config.py`
- `backend/app/services/alphasignal/alphasignal_client.py`
- `backend/app/services/alphasignal/memory.py`
- `backend/app/services/alphasignal/agent.py`
- `shared/schemas/alphasignal.py`
- `tests/backend/test_alphasignal_memory.py`
- `.env.example`
- `README.md`

### Rationale
The agent previously processed only the newest unseen newsletter per run. Batch processing with an optional start date supports daily catch-up (multiple emails per run) and controlled backfills without touching the existing dedup key format.

### Breaking Changes
None

### Next Steps
- Set `ALPHASIGNAL_START_DATE` in `.env` for initial backfill, then leave unset or adjust as needed
- Rebuild Docker and verify multi-edition runs in logs and LangSmith traces

## [2026-05-31 12:00] - BUGFIX

### Changes
- Fixed archive API pagination to build all page URLs from `ALPHASIGNAL_ARCHIVE_API_URL` instead of reconstructing from `ALPHASIGNAL_BASE_URL`
- Page 1 and subsequent backfill pages now share the same host, path, `limit`, and any other query parameters
- Added unit tests for `_build_archive_api_url`

### Files Modified
- `backend/app/services/alphasignal/alphasignal_client.py`
- `tests/backend/test_alphasignal_client.py`
- `README.md`

### Rationale
Page 1 used the configured archive API URL while page 2+ ignored it and rebuilt URLs from base URL and `ALPHASIGNAL_ARCHIVE_LIMIT`, causing mismatched pagination when env vars were customized.

### Breaking Changes
None

### Next Steps
None
