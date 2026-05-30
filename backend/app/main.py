"""FastAPI application with health endpoint."""

from __future__ import annotations

from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI


def create_app(scheduler: BackgroundScheduler | None = None) -> FastAPI:
    """Create FastAPI app for health checks and scheduler status."""
    app = FastAPI(
        title="AI Watch - AlphaSignal Agent",
        description="Daily AlphaSignal newsletter monitoring agent",
        version="1.0.0",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        jobs = []
        if scheduler:
            for job in scheduler.get_jobs():
                jobs.append(
                    {
                        "id": job.id,
                        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    }
                )
        return {"status": "ok", "scheduler_jobs": jobs}

    @app.post("/run-now")
    async def run_now() -> dict[str, str]:
        """Manually trigger the AlphaSignal job (useful for testing)."""
        from backend.app.jobs.run_daily_alphasignal import main as run_job

        exit_code = run_job(trigger="manual_api")
        return {
            "status": "ok" if exit_code == 0 else "error",
            "message": "Job triggered",
        }

    return app


app = create_app()
