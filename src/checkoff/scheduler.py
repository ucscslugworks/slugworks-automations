"""Long-running scheduler for the walkthrough check-off jobs.

Started alongside the Bambu manager by ./start_bambu, and stopped the same way.
It runs in its own process rather than inside the manager loop because a Canvas
roster scan takes far longer than the manager's cycle and would stall print
matching.

Schedule (intervals live in src/constants.py):
    grade      hourly - form responses to Canvas grades
    transfer   hourly - carry completions between course offerings
    staff      daily  - refresh the staff allow-list
    digest     weekly - email a summary of everything that changed

State is kept in checkoff_schedule.json at the repository root so a restart
does not re-fire every job or lose the week's accumulated events.
"""

import json
import os
import time
import traceback
from datetime import datetime, timedelta
from typing import Callable, Optional

from src import constants, log
from src.checkoff import digest, grade, staff, transfer
from src.checkoff.config import ROOT, Config, ConfigError
from src.checkoff.config import load as load_config

logger = log.setup_logs("checkoff", log.INFO)

STATE_FILE = os.path.join(ROOT, "checkoff_schedule.json")
PID_FILE = os.path.join(ROOT, "pid_checkoff")
STOP_FILE = os.path.join(ROOT, "common", "SPECIAL_BAMBU_STOP")

# Keep the report from growing without bound if it cannot be sent for weeks.
MAX_EVENTS = 2000

# Wait this long before retrying a weekly report that failed to send.
DIGEST_RETRY = 60 * 60


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    state.setdefault("last", {})  # job name -> unix time of last successful run
    state.setdefault("events", [])  # what changed, drained by the weekly digest
    state.setdefault("week_start", time.time())
    return state


def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)  # atomic, so a crash cannot truncate it


def record(state: dict, event: dict) -> None:
    event["at"] = time.time()
    state["events"].append(event)
    if len(state["events"]) > MAX_EVENTS:
        del state["events"][: len(state["events"]) - MAX_EVENTS]


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def due(state: dict, job: str, interval: float, now: float) -> bool:
    return now - state["last"].get(job, 0) >= interval


def digest_due(state: dict, now: float) -> bool:
    """True once a week, on the configured weekday and hour or later."""
    last = state["last"].get("digest", 0)
    moment = datetime.fromtimestamp(now)

    if moment.weekday() != constants.CHECKOFF_REPORT_WEEKDAY:
        return False
    if moment.hour < constants.CHECKOFF_REPORT_HOUR:
        return False
    # Back off after a failed send rather than retrying every cycle all evening.
    if now - state["last"].get("digest_attempt", 0) < DIGEST_RETRY:
        return False
    # Six days of slack, so a machine that was down on Friday still reports.
    return now - last >= timedelta(days=6).total_seconds()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def run_grade(cfg: Config, state: dict) -> None:
    summary = grade.run(cfg)
    if summary["results"]:
        record(state, {"job": "grade", **summary})


def run_transfer(cfg: Config, state: dict) -> None:
    pairs = transfer.pairs_from_config(cfg)
    if not pairs:
        logger.info("scheduler: no transfer pairs configured, skipping")
        return

    options = cfg.section("schedule")
    dry_run = not bool(options.get("transfer_apply", True))

    results = transfer.run(cfg, pairs, dry_run=dry_run)
    # Only worth reporting when something actually moved.
    if any(r.get("ok") or r.get("fail") for r in results):
        record(state, {"job": "transfer", "pairs": results})


def run_staff(cfg: Config, state: dict) -> None:
    cached = staff.read_cache(cfg)

    refreshed = staff.refresh(cfg)
    after = set(refreshed.members)

    if cached is None:
        # First run on this machine - no baseline, so report the size only
        # rather than listing every member as newly added.
        added, removed = [], []
    else:
        before = set(cached.members)
        added, removed = sorted(after - before), sorted(before - after)
    record(
        state,
        {
            "job": "staff",
            "count": len(after),
            "added": added,
            "removed": removed,
        },
    )
    if added or removed:
        logger.info("scheduler: staff added=%s removed=%s", added, removed)


def run_digest(cfg: Config, state: dict) -> None:
    now = time.time()
    state["last"]["digest_attempt"] = now
    subject, body = digest.build(state["events"], state["week_start"], now)
    if digest.send(cfg, subject, body):
        # Only clear the week once it has actually gone out.
        state["events"] = []
        state["week_start"] = now
    else:
        raise RuntimeError("weekly report could not be sent")


JOBS = (
    ("grade", constants.CHECKOFF_GRADE_INTERVAL, run_grade),
    ("transfer", constants.CHECKOFF_TRANSFER_INTERVAL, run_transfer),
    ("staff", constants.CHECKOFF_STAFF_INTERVAL, run_staff),
)


def attempt(name: str, cfg: Config, state: dict, job: Callable) -> None:
    """Run one job, recording failures instead of stopping the loop."""
    logger.info("scheduler: running %s", name)
    try:
        job(cfg, state)
        state["last"][name] = time.time()
        logger.info("scheduler: %s finished", name)
    except Exception:
        logger.error("scheduler: %s failed: %s", name, traceback.format_exc())
        record(
            state,
            {
                "job": "error",
                "which": name,
                "error": traceback.format_exc(limit=1).strip(),
            },
        )
        # Do not update last-run, so a transient failure retries next cycle.


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def scheduler() -> None:
    try:
        cfg = load_config()
    except ConfigError as e:
        logger.error("scheduler: %s", e)
        print(f"scheduler: {e}")
        return

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    logger.warning("scheduler: started (pid=%d)", os.getpid())

    state = load_state()

    try:
        while True:
            if os.path.exists(STOP_FILE):
                logger.warning("scheduler: stop file present, exiting")
                break

            now = time.time()
            for name, interval, job in JOBS:
                if due(state, name, interval, now):
                    attempt(name, cfg, state, job)

            if digest_due(state, now):
                attempt("digest", cfg, state, run_digest)

            save_state(state)
            time.sleep(constants.CHECKOFF_DELAY)

    except KeyboardInterrupt:
        logger.warning("scheduler: keyboard interrupt")
    except Exception:
        logger.error("scheduler: %s", traceback.format_exc())
    finally:
        save_state(state)
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        logger.warning("scheduler: stopped")


if __name__ == "__main__":
    scheduler()
