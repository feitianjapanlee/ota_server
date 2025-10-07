from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, models
from .config import get_config
from .database import SessionLocal

logger = logging.getLogger(__name__)


class RolloutScheduler:
    def __init__(self) -> None:
        config = get_config()
        self.scheduler = AsyncIOScheduler(timezone=config.scheduler.timezone)
        self.config = config

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            self.refresh_jobs()
            logger.info("Rollout scheduler started")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Rollout scheduler stopped")

    def refresh_jobs(self, *, apply_jobs: bool = True) -> None:
        config_path = Path(self.config.scheduler.schedules_file).resolve()
        if not config_path.exists():
            logger.warning("Schedules file %s not found", config_path)
            return
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        schedules: list[dict[str, Any]] = data.get("schedules", [])
        known_job_ids = {job.id for job in self.scheduler.get_jobs()} if apply_jobs else set()
        desired_job_ids: set[str] = set()

        with SessionLocal() as session:
            for item in schedules:
                name = item.get("name")
                rollout_name = item.get("rollout")
                cron_expression = item.get("cron")
                enabled = bool(item.get("enabled", True))
                if not name or not rollout_name or not cron_expression:
                    logger.warning("Invalid schedule definition: %s", item)
                    continue
                if apply_jobs:
                    desired_job_ids.add(name)
                rollout = self._get_rollout_by_name(session, rollout_name)
                if not rollout:
                    logger.warning("Rollout '%s' referenced by schedule '%s' not found", rollout_name, name)
                    continue
                crud.ensure_schedule(
                    session,
                    name=name,
                    rollout=rollout,
                    cron=cron_expression,
                    enabled=enabled,
                )
                if not apply_jobs:
                    continue
                if enabled:
                    trigger = CronTrigger.from_crontab(cron_expression, timezone=self.config.scheduler.timezone)
                    self.scheduler.add_job(
                        self.activate_rollout,
                        trigger=trigger,
                        id=name,
                        replace_existing=True,
                        kwargs={"rollout_name": rollout_name},
                    )
                    logger.info("Scheduled rollout '%s' via job '%s'", rollout_name, name)
                else:
                    # ensure disabled jobs are removed if they existed
                    if name in known_job_ids:
                        try:
                            self.scheduler.remove_job(job_id=name)
                        except Exception:  # pragma: no cover - APScheduler raises when missing
                            pass
                        else:
                            logger.info("Removed disabled schedule '%s'", name)
            session.commit()

        # prune orphaned jobs not present anymore
        if apply_jobs:
            for job_id in known_job_ids - desired_job_ids:
                try:
                    self.scheduler.remove_job(job_id=job_id)
                except Exception:  # pragma: no cover
                    continue
                logger.info("Removed stale schedule job '%s'", job_id)

    @staticmethod
    def _get_rollout_by_name(session: Session, name: str) -> models.Rollout | None:
        return session.execute(
            select(models.Rollout).where(models.Rollout.name == name)
        ).scalar_one_or_none()

    @staticmethod
    def activate_rollout(*, rollout_name: str) -> None:
        logger.info("Activating rollout '%s' via scheduler", rollout_name)
        with SessionLocal() as session:
            rollout = session.execute(
                select(models.Rollout).where(models.Rollout.name == rollout_name)
            ).scalar_one_or_none()
            if not rollout:
                logger.warning("Rollout '%s' not found during activation", rollout_name)
                return
            crud.set_rollout_status(
                session,
                rollout,
                status=models.RolloutStatus.active,
                is_active=True,
            )
            session.commit()
            logger.info("Rollout '%s' is now active", rollout_name)
