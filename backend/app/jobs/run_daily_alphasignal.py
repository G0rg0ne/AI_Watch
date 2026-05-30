"""Daily AlphaSignal agent job entrypoint."""

from __future__ import annotations

import logging
import sys

from backend.app.db.database import SessionLocal, init_db
from backend.app.services.alphasignal.agent import run_alphasignal_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main(trigger: str = "cli") -> int:
    """Run one AlphaSignal agent cycle."""
    init_db()
    db = SessionLocal()
    try:
        result = run_alphasignal_agent(db, trigger=trigger)
        logger.info("Run finished: status=%s message=%s", result.status, result.message)
        return 0 if result.status != "error" else 1
    except Exception:
        logger.exception("AlphaSignal agent run failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
