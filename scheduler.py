"""
Scheduler for automated daily / monthly pipeline runs.

Option A — Python scheduler (no OS dependency):
  python scheduler.py

Option B — Linux cron (recommended for production):
  Add to crontab: 0 7 * * 1-5 /path/to/venv/bin/python /path/to/main.py
  (runs at 07:00 Mon-Fri)

Option C — Windows Task Scheduler:
  Action: python main.py
  Trigger: daily at 07:00

This file implements Option A using the `schedule` library.
"""

import subprocess
import sys
import time
from datetime import datetime

import schedule

from config.settings import DAILY_RUN_TIME, REFRESH_FREQUENCY
from utils.logger import get_logger

log = get_logger("scheduler")


def run_pipeline():
    log.info(f"Scheduled pipeline triggered at {datetime.now().isoformat()}")
    result = subprocess.run(
        [sys.executable, "main.py"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log.info("Pipeline completed successfully")
        log.info(result.stdout)
    else:
        log.error(f"Pipeline failed (exit code {result.returncode})")
        log.error(result.stderr)


def setup_schedule():
    if REFRESH_FREQUENCY == "daily":
        # Run Mon-Fri at configured time
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            getattr(schedule.every(), day).at(DAILY_RUN_TIME).do(run_pipeline)
        log.info(f"Scheduled daily run at {DAILY_RUN_TIME} Mon-Fri")
    elif REFRESH_FREQUENCY == "monthly":
        # Run on the first day of each month
        schedule.every().day.at(DAILY_RUN_TIME).do(_run_if_first_of_month)
        log.info(f"Scheduled monthly run on 1st of month at {DAILY_RUN_TIME}")


def _run_if_first_of_month():
    if datetime.now().day == 1:
        run_pipeline()


if __name__ == "__main__":
    log.info("Starting financial automation scheduler")
    setup_schedule()

    # Run immediately on start
    run_pipeline()

    while True:
        schedule.run_pending()
        time.sleep(60)
