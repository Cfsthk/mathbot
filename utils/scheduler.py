"""
utils/scheduler.py — MathBot MVP v2.0
All nightly scheduled jobs registered with APScheduler via JobQueue.

Schedule (HKT = UTC+8):
  19:45  R1 reminder to class channels
  20:00  R1 battle opens (groups formed, DMs sent)
  20:15  R1 battle closes (auto-resolve unanswered)
  20:15  R2 solo sessions unlock (students may start their 5-question set)
  22:00  R2 sessions hard-close (protect sleep)
  00:00  Midnight: expire pending R3 challenges, reset nightly flags,
                   take nightly XP snapshot, check/award badges
  00:05  Weekly tournament resolve (Sundays only — checked inside job)
  00:10  Weekly tournament start  (Mondays only — checked inside job)
"""
import logging
from datetime import time

import pytz
from telegram.ext import Application

import config

logger = logging.getLogger(__name__)


def setup_jobs(application: Application) -> None:
    """
    Register all scheduled jobs with the application's JobQueue.
    Must be called after application is built (in main.py before run_polling).
    """
    jq = application.job_queue
    tz = pytz.timezone(config.TIMEZONE)

    # Lazy imports to avoid circular dependency
    from handlers.round1 import open_r1_battles, close_r1_battles
    from handlers.round2 import open_r2_sessions, close_r2_sessions
    from handlers.round3 import expire_r3_challenges
    from utils.nightly import (
        send_r1_reminder,
        midnight_reset,
        weekly_tournament_resolve,
        weekly_tournament_start,
    )

    def t(hour: int, minute: int) -> time:
        return time(hour=hour, minute=minute, second=0, tzinfo=tz)

    # 19:45 — R1 reminder in class channels
    jq.run_daily(
        send_r1_reminder,
        time=t(config.R1_REMINDER_HOUR, config.R1_REMINDER_MINUTE),
        name="r1_reminder",
    )
    logger.info("Scheduled: R1 reminder at %02d:%02d HKT", config.R1_REMINDER_HOUR, config.R1_REMINDER_MINUTE)

    # 20:00 — R1 opens
    jq.run_daily(
        open_r1_battles,
        time=t(config.R1_HOUR, config.R1_MINUTE),
        name="r1_open",
    )
    logger.info("Scheduled: R1 open at %02d:%02d HKT", config.R1_HOUR, config.R1_MINUTE)

    # 20:15 — R1 closes + R2 unlocks (both fire at same time, order matters)
    r1_close_minute = config.R1_MINUTE + config.R1_DURATION_MINUTES
    r1_close_hour = config.R1_HOUR + r1_close_minute // 60
    r1_close_minute = r1_close_minute % 60

    jq.run_daily(
        close_r1_battles,
        time=t(r1_close_hour, r1_close_minute),
        name="r1_close",
    )
    logger.info("Scheduled: R1 close at %02d:%02d HKT", r1_close_hour, r1_close_minute)

    jq.run_daily(
        open_r2_sessions,
        time=t(r1_close_hour, r1_close_minute),
        name="r2_open",
    )
    logger.info("Scheduled: R2 open at %02d:%02d HKT", r1_close_hour, r1_close_minute)

    # 22:00 — R2 hard close
    jq.run_daily(
        close_r2_sessions,
        time=t(config.R2_CLOSE_HOUR, config.R2_CLOSE_MINUTE),
        name="r2_close",
    )
    logger.info("Scheduled: R2 close at %02d:%02d HKT", config.R2_CLOSE_HOUR, config.R2_CLOSE_MINUTE)

    # 00:00 — Midnight reset (expire R3, reset flags, snapshot, badges)
    jq.run_daily(
        midnight_reset,
        time=t(config.MIDNIGHT_HOUR, config.MIDNIGHT_MINUTE),
        name="midnight_reset",
    )
    logger.info("Scheduled: midnight reset at 00:00 HKT")

    # 00:05 — Weekly tournament resolve (Sunday nights)
    jq.run_daily(
        weekly_tournament_resolve,
        time=t(0, 5),
        name="weekly_tournament_resolve",
    )
    logger.info("Scheduled: weekly tournament resolve check at 00:05 HKT")

    # 00:10 — Weekly tournament start (Monday nights)
    jq.run_daily(
        weekly_tournament_start,
        time=t(0, 10),
        name="weekly_tournament_start",
    )
    logger.info("Scheduled: weekly tournament start check at 00:10 HKT")
