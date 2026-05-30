---
name: add-agent-service
description: Add a new processing step or integration to the AlphaSignal agent pipeline. Use when extending the agent with a new service, adding a new data source, or wiring in a new external API (e.g. Slack notifier, RSS feed, secondary summarizer).
disable-model-invocation: true
---

# Add Agent Service

## Checklist

- [ ] Create service module under `backend/app/services/alphasignal/`
- [ ] Add Pydantic schema to `shared/schemas/alphasignal.py` if new data types
- [ ] Wrap every external call with `@traceable_step`
- [ ] Inject via `AlphaSignalAgent.__init__` (never instantiate inside `run()`)
- [ ] Write a test that mocks the service and covers the new path
- [ ] Update `README.md` and `DEVELOPMENT.md`
- [ ] Update `.env.example` if new env vars

## Service template

```python
# backend/app/services/alphasignal/my_service.py
from __future__ import annotations

import logging
from backend.app.core.config import Settings, get_settings
from backend.app.services.tracing import traceable_step

logger = logging.getLogger(__name__)


class MyService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @traceable_step("my_service_action")
    def action(self, data: str) -> str:
        logger.info("MyService.action called")
        # implementation
        return data
```

## Wire into the agent

In `backend/app/services/alphasignal/agent.py`:

```python
# 1. Add to __init__ signature
def __init__(self, ..., my_service: MyService | None = None) -> None:
    self.my_service = my_service or MyService(self.settings)

# 2. Call in run()
result = self.my_service.action(some_data)
```

## Test pattern

```python
my_service = MagicMock()
my_service.action.return_value = "mocked"
agent = AlphaSignalAgent(db=db_session, my_service=my_service)
result = agent.run()
my_service.action.assert_called_once()
```

## Tracing step names

Use lowercase with underscores describing the action:
- `tavily_fetch_newsletter` ✅
- `openai_summarize` ✅
- `FetchNewsletter` ❌
