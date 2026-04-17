"""Generator cron: poll fetcher for payload-hash changes, enqueue rebuilds.

Run as its own container: CMD python -m src.cron
"""
import logging
import time

from . import config, db, fetcher_client

log = logging.getLogger("generator.cron")


def tick() -> dict:
    enqueued = 0
    failed = 0
    for username in db.list_enrolled():
        try:
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
    return {"enqueued": enqueued, "failed": failed}


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
