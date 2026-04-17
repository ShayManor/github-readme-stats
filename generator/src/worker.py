"""Build worker. Pulls pending jobs and renders widgets.

Run as its own container: CMD python -m src.worker
"""
import logging
import time

from . import cache, config, db, fetcher_client, placeholder, processor
from .widgets import compose_widget

log = logging.getLogger("generator.worker")
MAX_ATTEMPTS = 3


def _render_widgets(username: str, payload: dict, settings: dict) -> dict[str, str]:
    enabled = settings.get("enabled") or config.ENABLED_WIDGETS
    order = settings.get("widget_order") or config.WIDGET_ORDER
    theme = settings.get("theme", "dark")
    widgets = processor.generate_widgets_from_github(
        payload,
        theme=theme,
        custom_tags=settings.get("custom_tags"),
        hidden_languages=settings.get("hidden_languages"),
        enabled=enabled,
        widget_settings=settings.get("widget_settings") or {},
    )
    ordered = [w for w in order if w in enabled and w in widgets and widgets[w]]
    composite = compose_widget(
        widgets=widgets, enabled=ordered, theme_name=theme,
        username=username, avatar_b64=payload.get("avatar_b64", ""),
    )
    out = {name: svg for name, svg in widgets.items() if svg}
    out["composite"] = composite
    return out


def process_one() -> bool:
    job = db.claim_next_job()
    if job is None:
        return False
    username = job["username"]
    try:
        result = fetcher_client.get_data(username)
        payload = result.get("data") or {}
        if payload.get("error") == "not_found":
            svg = placeholder.render("not_found", username, theme="dark")
            db.put_widgets(username, "not_found", {"composite": svg})
            cache.Cache().delete(f"widget:composite:{username}")
            db.complete_job(job["id"])
            log.info("not_found marker persisted for %s", username)
            return True

        settings_row = db.get_settings(username)
        if settings_row is None:
            db.fail_job(job["id"], "settings missing", retry=False)
            return True

        widgets = _render_widgets(username, payload, settings_row["settings"])
        db.put_widgets(username, settings_row["settings_hash"], widgets)
        db.set_last_fetcher_hash(username, result.get("payload_hash", ""))
        db.lru_trim(username, config.WIDGET_LRU_PER_USER)
        c = cache.Cache()
        c.delete(f"widget:composite:{username}", *[f"widget:{n}:{username}" for n in widgets])
        db.complete_job(job["id"])
        log.info("built widgets for %s", username)
        return True
    except Exception as e:
        retry = job["attempts"] < MAX_ATTEMPTS
        db.fail_job(job["id"], str(e)[:500], retry=retry)
        log.warning("build failed for %s (retry=%s): %s", username, retry, e)
        return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_dbs()
    while True:
        db.reclaim_stuck_jobs(older_than_minutes=10)
        if not process_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
