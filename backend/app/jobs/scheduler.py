"""Internal APScheduler for daily AlphaSignal checks."""

from __future__ import annotations

import logging
import sys
import threading

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.core.config import get_settings
from backend.app.db.database import SessionLocal, init_db
from backend.app.jobs.run_daily_alphasignal import main as run_job
from backend.app.main import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _run_job(trigger: str) -> None:
    """Wrapper invoked by APScheduler."""
    logger.info("AlphaSignal job triggered by %s", trigger)
    exit_code = run_job(trigger=trigger)
    if exit_code != 0:
        logger.error("AlphaSignal job completed with errors (exit code %s)", exit_code)


def _scheduled_job() -> None:
    """Run the daily AlphaSignal job from APScheduler."""
    _run_job(trigger="scheduler")


def start_scheduler() -> BackgroundScheduler:
    """Configure and start the daily scheduler."""
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _scheduled_job,
        trigger=CronTrigger(
            hour=settings.run_hour_utc,
            minute=settings.run_minute_utc,
        ),
        id="daily_alphasignal",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: daily run at %02d:%02d UTC",
        settings.run_hour_utc,
        settings.run_minute_utc,
    )
    return scheduler


def main() -> None:
    """Start health API and internal daily scheduler."""
    settings = get_settings()
    init_db()

    scheduler = start_scheduler()
    if settings.run_on_startup:
        logger.info("Running AlphaSignal job immediately on startup")
        threading.Thread(target=_run_job, kwargs={"trigger": "startup"}, daemon=True).start()

    app = create_app(scheduler=scheduler)
    try:
        uvicorn.run(app, host=settings.app_host, port=settings.app_port, log_level="info")
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
