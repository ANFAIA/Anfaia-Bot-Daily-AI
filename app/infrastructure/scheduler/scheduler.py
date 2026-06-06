"""Daily scheduler based on APScheduler (AsyncIOScheduler).

Schedules the workflow to run at the configured time (`POST_TIME`) in the given
time zone (`TIMEZONE`). Reuses the application's event loop.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.application.use_cases import RunDailyWorkflowUseCase, RunWeeklyNewsletterUseCase
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_JOB_ID = "daily_news_workflow"
_NEWSLETTER_JOB_ID = "weekly_newsletter_workflow"


class DailyScheduler:
    """Encapsulates the lifecycle of the daily publication scheduler."""

    def __init__(self, settings: Settings, run_workflow_uc: RunDailyWorkflowUseCase) -> None:
        self._settings = settings
        self._uc = run_workflow_uc
        self._scheduler = AsyncIOScheduler(timezone=settings.timezone)

    async def _job(self) -> None:
        logger.info("scheduler.trigger", job=_JOB_ID)
        try:
            await self._uc.execute()
        except Exception:
            logger.exception("scheduler.job_failed")

    def start(self) -> None:
        if not self._settings.scheduler_enabled:
            logger.info("scheduler.disabled")
            return
        trigger = CronTrigger(
            hour=self._settings.post_hour,
            minute=self._settings.post_minute,
            timezone=self._settings.timezone,
        )
        self._scheduler.add_job(
            self._job,
            trigger=trigger,
            id=_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "scheduler.started",
            post_time=self._settings.post_time,
            timezone=self._settings.timezone,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler.stopped")


class WeeklyScheduler:
    """Encapsulates the lifecycle of the weekly newsletter scheduler."""

    def __init__(self, settings: Settings, run_newsletter_uc: RunWeeklyNewsletterUseCase) -> None:
        self._settings = settings
        self._uc = run_newsletter_uc
        self._scheduler = AsyncIOScheduler(timezone=settings.timezone)

    async def _job(self) -> None:
        logger.info("scheduler.trigger", job=_NEWSLETTER_JOB_ID)
        try:
            await self._uc.execute()
        except Exception:
            logger.exception("scheduler.job_failed", job=_NEWSLETTER_JOB_ID)

    def start(self) -> None:
        if not self._settings.newsletter_enabled:
            logger.info("scheduler.newsletter_disabled")
            return
        trigger = CronTrigger(
            day_of_week=self._settings.newsletter_day_of_week,
            hour=self._settings.newsletter_post_hour,
            minute=self._settings.newsletter_post_minute,
            timezone=self._settings.timezone,
        )
        self._scheduler.add_job(
            self._job,
            trigger=trigger,
            id=_NEWSLETTER_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "scheduler.newsletter_started",
            day_of_week=self._settings.newsletter_day_of_week,
            post_time=self._settings.newsletter_post_time,
            timezone=self._settings.timezone,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler.newsletter_stopped")
