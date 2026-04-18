"""Prefetch worker. Pulls pending jobs and populates widget data.

Two-phase pipeline:
  * Phase 1 (this module): on enroll/settings-change, fetch the raw GitHub
    payload from the fetcher and compute widget data for the client-side
    Workshop preview. No SVG rendering.
  * Phase 2 (render_widgets_now, called from the API's Generate endpoint):
    synchronously render composite SVG from the cached raw + current
    settings and persist to widgets.db.

This split keeps the fetcher hot while the user edits settings and defers
expensive SVG composition until the user clicks Generate.

Run as its own container: CMD python -m src.worker
"""
import logging
import time
from dataclasses import asdict

from . import cache, config, db, fetcher_client, placeholder, processor
from .widgets import compose_widget

log = logging.getLogger("generator.worker")
MAX_ATTEMPTS = 3


def _compute_widget_data(payload: dict, settings: dict) -> dict:
    """Compute raw widget data dict for client-side rendering."""
    custom_tags = settings.get("custom_tags")
    hidden_languages = settings.get("hidden_languages")
    return {
        "grade": asdict(processor.compute_grade(payload, custom_tags=custom_tags)),
        "impact": [asdict(w) for w in processor.compute_impact_timeline(payload)],
        "collaborators": [asdict(c) for c in processor.compute_collaborators(payload)],
        "focus": [asdict(f) for f in processor.compute_focus(payload, hidden_languages=hidden_languages)],
        "languages": [asdict(l) for l in processor.compute_languages(payload, hidden_languages=hidden_languages)],
    }


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
    """Phase 1: claim a pending job and populate widget data (no SVG)."""
    job = db.claim_next_job()
    if job is None:
        return False
    username = job["username"]
    try:
        result = fetcher_client.get_data(username)
        payload = result.get("data") or {}
        if payload.get("error") == "not_found":
            db.put_widget_data(username, "not_found", {"not_found": True})
            db.point_current_widget(username, "not_found")
            db.complete_job(job["id"])
            log.info("not_found marker persisted for %s", username)
            return True

        settings_row = db.get_settings(username)
        if settings_row is None:
            db.fail_job(job["id"], "settings missing", retry=False)
            return True

        widget_data = _compute_widget_data(payload, settings_row["settings"])
        db.put_widget_data(username, settings_row["settings_hash"], widget_data)
        db.point_current_widget(username, settings_row["settings_hash"])
        db.set_last_fetcher_hash(username, result.get("payload_hash", ""))
        db.lru_trim(username, config.WIDGET_LRU_PER_USER)
        db.complete_job(job["id"])
        log.info("prefetched data for %s", username)
        return True
    except Exception as e:
        retry = job["attempts"] < MAX_ATTEMPTS
        db.fail_job(job["id"], str(e)[:500], retry=retry)
        log.warning("prefetch failed for %s (retry=%s): %s", username, retry, e)
        return True


def render_widgets_now(username: str) -> dict[str, str]:
    """Phase 2: synchronously render composite SVG and persist it.

    Called from POST /api/<u>/generate. Reuses the fetcher's cached payload
    (a cheap internal HTTP lookup) so the user-facing render is fast even
    if the prefetch job hasn't drained from the queue yet.
    """
    settings_row = db.get_settings(username)
    if settings_row is None:
        raise LookupError("not_enrolled")
    result = fetcher_client.get_data(username)
    payload = result.get("data") or {}
    if payload.get("error") == "not_found":
        svg = placeholder.render("not_found", username, theme=settings_row["settings"].get("theme", "dark"))
        db.put_widgets(username, "not_found", {"composite": svg})
        db.point_current_widget(username, "not_found")
        cache.Cache().delete(f"widget:composite:{username}")
        return {"composite": svg}

    widgets = _render_widgets(username, payload, settings_row["settings"])
    db.put_widgets(username, settings_row["settings_hash"], widgets)
    db.point_current_widget(username, settings_row["settings_hash"])
    c = cache.Cache()
    c.delete(f"widget:composite:{username}", *[f"widget:{n}:{username}" for n in widgets])
    log.info("rendered widgets on-demand for %s", username)
    return widgets


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_dbs()
    while True:
        db.reclaim_stuck_jobs(older_than_minutes=10)
        if not process_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
