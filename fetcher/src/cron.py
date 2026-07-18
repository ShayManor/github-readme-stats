"""Scheduled refresh + GC loop. Run as its own container (CMD override)."""
import logging
import time

from . import config, db, github

log = logging.getLogger("fetcher.cron")


def tick(hours: int, active_within_days: int, gc_days: int) -> dict:
    """Refresh due users, then GC abandoned ones. Returns counts."""
    refreshed = 0
    failed = 0
    due = db.users_due_for_refresh(hours=hours, active_within_days=active_within_days)
    for username in due:
        try:
            data = github.fetch_github_data(username, token=config.GITHUB_PAT)
            user = data.get("user")
            if user is None or (isinstance(user, dict) and user.get("message") == "Not Found"):
                data = {"error": "not_found"}
                db.bump_fetch_metric("not_found")
            else:
                db.bump_fetch_metric("ok")
            db.upsert_user(username, data)
            refreshed += 1
        except github.GitHubTransientError as e:
            db.bump_fetch_metric("rate_limited")
            log.warning("refresh rate-limited for %s (kept last-good): %s", username, e)
            failed += 1
        except Exception as e:
            db.bump_fetch_metric("error")
            log.warning("refresh failed for %s: %s", username, e)
            failed += 1
    gc_removed = db.delete_stale(days=gc_days)
    return {"refreshed": refreshed, "failed": failed, "gc_removed": gc_removed}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_db()
    interval = 3600  # 1h between ticks
    while True:
        try:
            stats = tick(
                hours=config.REFRESH_INTERVAL_HOURS,
                active_within_days=config.TRIAL_GC_DAYS,
                gc_days=config.TRIAL_GC_DAYS,
            )
            log.info("tick complete: %s", stats)
        except Exception:
            log.exception("tick failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
