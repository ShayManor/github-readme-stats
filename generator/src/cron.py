"""Generator cron: poll fetcher for payload-hash changes, enqueue rebuilds.

Run as its own container: CMD python -m src.cron
"""
import logging
import os
import time

from . import config, db, fetcher_client

log = logging.getLogger("generator.cron")

# Pacing between users in a single tick. On a mini PC with N enrolled
# users, a tight loop would fire N fetcher calls back-to-back, each of
# which can become a GitHub call — trivially enough to spike CPU and
# burn PAT budget. Default 0.25s keeps 1000 users inside a ~4-minute
# tick while leaving headroom in the 15-minute window.
_TICK_INTER_USER_SLEEP_S = float(os.getenv("GENERATOR_CRON_INTER_USER_SLEEP_S", "0.25"))

# Queue-depth backstop. If the build worker is already behind, don't
# enqueue more: let it drain. Keeps SQLite from swelling when a burst of
# GitHub changes arrives at once.
_TICK_QUEUE_CAP = int(os.getenv("GENERATOR_CRON_QUEUE_CAP", str(config.PENDING_JOB_QUEUE_CAP)))


def tick() -> dict:
    enqueued = 0
    failed = 0
    skipped_queue_full = 0
    for username in db.list_enrolled():
        try:
            if db.pending_job_count() >= _TICK_QUEUE_CAP:
                skipped_queue_full += 1
                # Don't hammer the fetcher either when the queue is full.
                time.sleep(_TICK_INTER_USER_SLEEP_S)
                continue
            info = db.get_settings(username)
            current = info.get("last_fetcher_payload_hash")
            r = fetcher_client.get_data(username)
            latest = r.get("payload_hash")
            if latest and latest != current:
                db.enqueue_build(username)
                db.set_last_fetcher_hash(username, latest)
                enqueued += 1
        except Exception as e:
            log.warning("poll failed for %s: %s", username, e)
            failed += 1
        if _TICK_INTER_USER_SLEEP_S > 0:
            time.sleep(_TICK_INTER_USER_SLEEP_S)
    return {"enqueued": enqueued, "failed": failed, "skipped_queue_full": skipped_queue_full}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_dbs()
    interval_s = config.POLL_INTERVAL_MINUTES * 60
    while True:
        try:
            log.info("tick: %s", tick())
        except Exception:
            log.exception("tick failed")
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
