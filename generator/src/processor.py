"""GitHub data processing and widget generation."""

from datetime import datetime, timedelta, date
from collections import defaultdict

from .models import (
    GradeData,
    TagData,
    ImpactWeek,
    CollaboratorData,
    FocusCategory,
    LanguageData,
    AchievementData,
    StreakData,
)
from .widgets import (
    render_grade_widget,
    render_impact_widget,
    render_collaborators_widget,
    render_focus_widget,
    render_languages_widget,
    render_achievements_widget,
    render_streaks_widget,
)


def compute_grade(github_data: dict, custom_tags: list[str] = None) -> GradeData:
    """
    Compute a developer grade from GitHub profile data.

    Args:
        github_data: GitHub profile data dictionary
        custom_tags: Optional list of custom tags to include (e.g., ["open-source", "hackathon-winner"])
    """
    user = github_data["user"]
    repos = github_data["repos"]
    events = github_data["events"]

    # Use accurate contribution count (commits + PRs + issues + reviews) from GraphQL
    commits = github_data.get("total_commits", 0)

    # Fallback to daily contribution data if aggregation didn't work
    if commits == 0:
        daily_contribs = github_data.get("commits", [])
        if daily_contribs and isinstance(daily_contribs, list) and len(daily_contribs) > 0:
            if isinstance(daily_contribs[0], dict) and "count" in daily_contribs[0]:
                commits = sum(day.get("count", 0) for day in daily_contribs)
            else:
                commits = len(daily_contribs)
        else:
            commits = sum(
                len(ev.get("payload", {}).get("commits", []))
                for ev in events if ev.get("type") == "PushEvent"
            )

    repo_count = min(len(repos), 50)
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    forks = sum(r.get("forks_count", 0) for r in repos)
    followers = user.get("followers", 0)

    # Use accurate PR count from search API
    prs = github_data.get("total_prs", 0)

    # Fallback to events if not available
    if prs == 0:
        prs = sum(1 for ev in events if ev.get("type") == "PullRequestEvent")

    # Last-year consistency: count distinct ISO weeks with at least one
    # commit on the GitHub contribution calendar (which always covers the
    # trailing year). 40 active weeks out of ~52 tops this factor out, so
    # someone who works in bursts isn't penalised, but sporadic once-a-
    # quarter activity scores low.
    daily = github_data.get("commits", [])
    active_weeks: set = set()
    if isinstance(daily, list):
        for day in daily:
            if not isinstance(day, dict):
                continue
            if day.get("count", 0) <= 0:
                continue
            date_str = day.get("date")
            if not isinstance(date_str, str):
                continue
            try:
                iso = date.fromisoformat(date_str).isocalendar()
                active_weeks.add((iso[0], iso[1]))
            except ValueError:
                continue

    # Weights sum to 1.0
    per_factor = {
        "commits":     (min(commits / 3000 * 100, 100), 0.33),
        "consistency": (min(len(active_weeks) / 40 * 100, 100), 0.22),
        "repos":       (min(repo_count / 40 * 100, 100), 0.15),
        "stars":       (min(stars / 200 * 100, 100), 0.11),
        "forks":       (min(forks / 20 * 100, 100), 0.08),
        "activity":    (min(len(events) / 80 * 100, 100), 0.08),
        "followers":   (min(followers / 100 * 100, 100), 0.03),
    }
    scores = {k: v for k, (v, _w) in per_factor.items()}
    total = sum(v * w for v, w in per_factor.values())

    # Grade scale
    if total >= 97:
        grade = "S++"
    elif total >= 93:
        grade = "S+"
    elif total >= 89:
        grade = "S"
    elif total >= 86:
        grade = "A++"
    elif total >= 82:
        grade = "A+"
    elif total >= 78:
        grade = "A"
    elif total >= 72:
        grade = "A-"
    elif total >= 68:
        grade = "B++"
    elif total >= 64:
        grade = "B+"
    elif total >= 58:
        grade = "B"
    elif total >= 50:
        grade = "B-"
    elif total >= 42:
        grade = "C+"
    else:
        # C is the floor. Anything that would previously have slid into C-,
        # D+, D, D-, or F is clamped up to C — the widget is meant to be an
        # encouraging profile snapshot, not a failure grade.
        grade = "C"

    stats = {
        "commits": commits,
        "prs": prs,
        "stars": stars,
        "repos": repo_count,
        "followers": followers,
    }

    tags = _compute_tags(github_data, custom_tags=custom_tags, hidden_languages=None)

    return GradeData(
        grade=grade,
        score=round(total, 1),
        stats=stats,
        tags=tags,
        breakdown={k: round(v, 1) for k, v in scores.items()},
    )


def _compute_tags(github_data: dict, max_tags: int = None, custom_tags: list[str] = None, hidden_languages: list[str] = None) -> list[TagData]:
    """
    Infer developer tags from repo languages and topics using percentage thresholds.

    Tags are awarded based on:
    - Frontend: >50% frontend languages
    - Backend: >50% backend languages
    - ML: >25% ML-related languages
    - Fullstack: >25% frontend AND >25% backend
    - Systems: >50% systems languages
    - DevOps: >25% DevOps-related languages
    - Mobile: >50% mobile languages

    Args:
        github_data: GitHub data dictionary
        max_tags: Maximum number of tags to return (1-20). Defaults to TAG_MAX_COUNT from config.
        custom_tags: Optional list of custom tags to add (e.g., ["open-source", "hackathon-winner"])
        hidden_languages: Optional list of languages to exclude from tag calculation

    Returns:
        List of TagData objects with inferred developer roles
    """
    from .config import TAG_MAX_COUNT, TAG_LANGUAGE_MAP, TAG_TOPIC_MAP, HIDDEN_LANGUAGES

    if max_tags is None:
        max_tags = TAG_MAX_COUNT
    max_tags = min(max(max_tags, 1), 20)  # Clamp between 1 and 20

    if hidden_languages is None:
        hidden_languages = HIDDEN_LANGUAGES

    repos = github_data["repos"]
    lang_counts = defaultdict(int)
    topic_set = set()

    for r in repos:
        lang = r.get("language")
        if lang and lang not in hidden_languages:
            lang_counts[lang] += 1
        for topic in r.get("topics", []):
            topic_set.add(topic.lower())

    tags = []
    total = sum(lang_counts.values()) or 1

    # Calculate percentage for each category
    category_percentages = defaultdict(float)

    for lang, count in lang_counts.items():
        pct = count / total
        for category in TAG_LANGUAGE_MAP.get(lang, []):
            category_percentages[category] += pct

    # Infer tags from repository topics
    for topic in topic_set:
        if topic in TAG_TOPIC_MAP:
            category = TAG_TOPIC_MAP[topic]
            category_percentages[category] = max(category_percentages[category], 0.3)

    # Apply threshold rules
    awarded_tags = []
    tag_label_overrides: dict[str, str] = {}

    # Fullstack: >25% frontend AND >25% backend
    if category_percentages.get("Frontend", 0) > 0.25 and category_percentages.get("Backend", 0) > 0.25:
        awarded_tags.append(("fullstack", max(category_percentages.get("Frontend", 0), category_percentages.get("Backend", 0))))

    # ML: >25%
    if category_percentages.get("ML", 0) > 0.25:
        awarded_tags.append(("ml-engineer", category_percentages["ML"]))

    # Backend: >50%
    if category_percentages.get("Backend", 0) > 0.50:
        awarded_tags.append(("backend", category_percentages["Backend"]))

    # Frontend: >50%
    if category_percentages.get("Frontend", 0) > 0.50:
        awarded_tags.append(("frontend", category_percentages["Frontend"]))

    # Systems: >50%
    if category_percentages.get("Systems", 0) > 0.50:
        awarded_tags.append(("systems", category_percentages["Systems"]))

    # DevOps: >25%
    if category_percentages.get("DevOps", 0) > 0.25:
        awarded_tags.append(("devops", category_percentages["DevOps"]))

    # Mobile: >50%
    if category_percentages.get("Mobile", 0) > 0.50:
        awarded_tags.append(("mobile", category_percentages["Mobile"]))

    # Database: >25%
    if category_percentages.get("Database", 0) > 0.25:
        awarded_tags.append(("database", category_percentages["Database"]))

    # Cloud: >25%
    if category_percentages.get("Cloud", 0) > 0.25:
        awarded_tags.append(("cloud", category_percentages["Cloud"]))

    # Security: >25%
    if category_percentages.get("Security", 0) > 0.25:
        awarded_tags.append(("security", category_percentages["Security"]))

    # Add custom tags with high confidence
    if custom_tags:
        for tag in custom_tags:
            awarded_tags.append((tag, 1.0))

    # Auto-awarded tags (username-specific + rule-based; see src/tag_rules.py).
    from . import tag_rules
    username = (github_data.get("user") or {}).get("login", "")
    for auto_tag, label in tag_rules.evaluate(username, github_data):
        awarded_tags.append((auto_tag, 1.0))
        if label:
            tag_label_overrides[auto_tag] = label

    # Sort by confidence and limit to max_tags
    for tag, conf in sorted(awarded_tags, key=lambda x: -x[1])[:max_tags]:
        tags.append(TagData(
            tag=tag,
            source="earned" if conf < 1.0 else "custom",
            confidence=round(conf, 2),
            label=tag_label_overrides.get(tag),
        ))

    return tags


def compute_impact_timeline(github_data: dict) -> list[ImpactWeek]:
    """Aggregate daily contributions into weekly impact data using GitHub's contribution calendar."""
    daily_contributions = github_data.get("commits", [])
    weekly = defaultdict(lambda: {"commits": 0})

    # Calculate date boundaries
    now = datetime.now()
    current_week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    six_months_ago = now - timedelta(days=180)

    if daily_contributions and isinstance(daily_contributions, list) and len(daily_contributions) > 0:
        # Use GraphQL daily contribution data (format: [{"date": "YYYY-MM-DD", "count": N}])
        if isinstance(daily_contributions[0], dict) and "date" in daily_contributions[0] and "count" in daily_contributions[0]:
            for day_data in daily_contributions:
                date_str = day_data.get("date", "")
                count = day_data.get("count", 0)

                if date_str:
                    dt = datetime.fromisoformat(date_str)

                    # Calculate week start (Monday)
                    week_start_dt = dt - timedelta(days=dt.weekday())
                    week_start_str = week_start_dt.isoformat()[:10]

                    # Only include last 6 months, excluding current week
                    if dt >= six_months_ago and week_start_dt < current_week_start:
                        weekly[week_start_str]["commits"] += count
        else:
            # Old REST API format fallback
            for commit in daily_contributions:
                commit_date = commit.get("commit", {}).get("author", {}).get("date", "")
                if commit_date:
                    created = commit_date[:10]
                    dt = datetime.fromisoformat(created)

                    # Calculate week start (Monday)
                    week_start_dt = dt - timedelta(days=dt.weekday())
                    week_start_str = week_start_dt.isoformat()[:10]

                    # Only include last 6 months, excluding current week
                    if dt >= six_months_ago and week_start_dt < current_week_start:
                        weekly[week_start_str]["commits"] += 1
    else:
        # Fallback to events-based counting
        events = github_data.get("events", [])
        for ev in events:
            if ev.get("type") == "PushEvent":
                created = ev.get("created_at", "")[:10]
                if created:
                    dt = datetime.fromisoformat(created)

                    # Calculate week start (Monday)
                    week_start_dt = dt - timedelta(days=dt.weekday())
                    week_start_str = week_start_dt.isoformat()[:10]

                    # Only include last 6 months, excluding current week
                    if dt >= six_months_ago and week_start_dt < current_week_start:
                        commits = len(ev.get("payload", {}).get("commits", []))
                        weekly[week_start_str]["commits"] += commits

    weeks = []
    for ws in sorted(weekly.keys()):
        d = weekly[ws]
        weeks.append(ImpactWeek(week_start=ws, commits=d["commits"]))

    return weeks


def compute_collaborators(github_data: dict) -> list[CollaboratorData]:
    """
    Return top collaborators from pre-scored data produced by _fetch_collaborators_data.

    The scoring (min(user_commits, their_commits) with owner boost and multi-repo
    weighting) happens in the fetcher so the widget just picks the top K.
    """
    scored = github_data.get("collaborators_data", [])

    # Fallback to events-based if collaborator scoring produced nothing
    if not scored:
        return _compute_collaborators_from_events(github_data)

    collabs = []
    for s in scored[:5]:
        collabs.append(
            CollaboratorData(
                username=s["login"],
                shared_repos=s["shared_repos"],
                shared_commits=int(round(s["raw_score"])),
                avatar_b64="",
            )
        )
    return collabs


def _compute_collaborators_from_events(github_data: dict) -> list[CollaboratorData]:
    """Fallback: compute collaborators from events (less accurate)."""
    events = github_data["events"]
    me = github_data["user"].get("login", "").lower()
    collab_stats = defaultdict(lambda: {"repos": set(), "commits": 0})

    for ev in events:
        actor = ev.get("actor", {}).get("login", "")
        if actor.lower() != me:
            repo = ev.get("repo", {}).get("name", "")
            collab_stats[actor]["repos"].add(repo)
            collab_stats[actor]["commits"] += 1

    collabs = []
    for username, stats in sorted(
        collab_stats.items(), key=lambda x: -x[1]["commits"]
    )[:4]:  # Match the main function: top 4
        collabs.append(
            CollaboratorData(
                username=username,
                shared_repos=len(stats["repos"]),
                shared_commits=stats["commits"],
            )
        )

    return collabs


def compute_focus(github_data: dict, hidden_languages: list[str] = None) -> list[FocusCategory]:
    """
    Classify contributions into focus categories based on repo languages weighted by activity.

    Args:
        github_data: GitHub profile data
        hidden_languages: Optional list of languages to exclude
    """
    from .config import HIDDEN_LANGUAGES

    if hidden_languages is None:
        hidden_languages = HIDDEN_LANGUAGES

    repos = github_data["repos"]
    total_contributions = github_data.get("recent_commits", 0)  # Last 6 months

    # Map languages to focus categories (languages can belong to multiple categories)
    lang_to_focus = {
        "Python": ["Backend", "ML"],
        "JavaScript": ["Frontend"],
        "TypeScript": ["Frontend"],
        "HTML": ["Frontend"],
        "CSS": ["Frontend"],
        "Vue": ["Frontend"],
        "React": ["Frontend"],
        "Go": ["Backend"],
        "Rust": ["Backend", "Systems"],
        "Java": ["Backend"],
        "C++": ["Systems"],
        "C": ["Systems"],
        "Ruby": ["Backend"],
        "PHP": ["Backend"],
        "Shell": ["DevOps"],
        "Dockerfile": ["DevOps"],
        "Makefile": ["DevOps"],
        "Jupyter Notebook": ["ML"],
        "R": ["ML"],
        "Scala": ["Backend", "ML"],
        "Kotlin": ["Backend", "Mobile"],
        "Swift": ["Mobile"],
        "Objective-C": ["Mobile"],
    }

    focus_counts = defaultdict(float)

    # Use top 30 most recently pushed repos
    sorted_repos = sorted(repos, key=lambda r: r.get("pushed_at", ""), reverse=True)
    active_repos = sorted_repos[:30]

    # Count languages in active repos (excluding hidden languages)
    lang_weights = defaultdict(int)
    for r in active_repos:
        lang = r.get("language")
        if lang and lang not in hidden_languages:
            lang_weights[lang] += 1

    total_weight = sum(lang_weights.values())

    # Distribute contributions proportionally to language presence
    if total_weight > 0 and total_contributions > 0:
        for lang, weight in lang_weights.items():
            contribution_estimate = (weight / total_weight) * total_contributions

            # Add to all applicable focus categories
            if lang in lang_to_focus:
                for focus in lang_to_focus[lang]:
                    focus_counts[focus] += contribution_estimate
            else:
                focus_counts["Other"] += contribution_estimate
    else:
        # Fallback: use repo counts
        for r in active_repos:
            lang = r.get("language")
            if lang in lang_to_focus:
                for focus in lang_to_focus[lang]:
                    focus_counts[focus] += 1
            elif lang:
                focus_counts["Other"] += 1

    # Use total contributions as the base for percentages (allows overlap > 100%)
    total = total_contributions if total_contributions > 0 else sum(focus_counts.values())
    total = total or 1

    return [
        FocusCategory(
            category=cat,
            percentage=round(count / total * 100, 1),
            commit_count=int(count),
        )
        for cat, count in sorted(focus_counts.items(), key=lambda x: -x[1])
    ]


def compute_languages(github_data: dict, hidden_languages: list[str] = None) -> list[LanguageData]:
    """
    Compute language distribution from repos.

    Prefers per-repo byte breakdowns (`repo["language_bytes"]`) when present —
    that matches GitHub's own "Most Used Languages" widget. Falls back to a
    primary-language repo-count tally for payloads fetched before the
    enrichment step landed.

    Args:
        github_data: GitHub profile data
        hidden_languages: Optional list of languages to exclude (e.g., ["HTML", "CSS"])
    """
    from .config import HIDDEN_LANGUAGES

    if hidden_languages is None:
        hidden_languages = HIDDEN_LANGUAGES
    hidden_set = {h for h in hidden_languages}

    repos = github_data["repos"]
    login = (github_data.get("user") or {}).get("login") or ""
    login_lc = login.lower()

    def _is_authored(r: dict) -> bool:
        # Repos the user mostly didn't write shouldn't dominate their
        # language mix. "Authored" = not a fork AND owned by the user
        # (or by an org where we can't easily tell, so stay conservative
        # and require personal ownership). This drops the big-fork /
        # random-org-contribution case that was skewing the widget.
        if r.get("fork"):
            return False
        owner_login = ((r.get("owner") or {}).get("login") or "").lower()
        return bool(owner_login) and owner_login == login_lc

    def _byte_tally(predicate) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for r in repos:
            if not predicate(r):
                continue
            lb = r.get("language_bytes") or {}
            if not isinstance(lb, dict):
                continue
            for lang, n in lb.items():
                if lang and lang not in hidden_set:
                    totals[lang] += int(n or 0)
        return totals

    # Preferred: bytes across authored repos only.
    byte_totals = _byte_tally(_is_authored)

    # Fallback ladder so the widget is never empty: if the user has no
    # authored repos with byte data (rare — new accounts, or everything
    # is a fork), expand to all non-fork repos, and finally to everything.
    if not byte_totals:
        byte_totals = _byte_tally(lambda r: not r.get("fork"))
    if not byte_totals:
        byte_totals = _byte_tally(lambda r: True)

    if byte_totals:
        total = sum(byte_totals.values()) or 1
        return [
            LanguageData(
                language=lang,
                percentage=round(size / total * 100, 1),
                loc=size,
            )
            for lang, size in sorted(byte_totals.items(), key=lambda x: -x[1])
        ]

    # Legacy fallback: repo-count by primary language, same ownership filter.
    lang_counts: dict[str, int] = defaultdict(int)
    for r in repos:
        if not _is_authored(r):
            continue
        lang = r.get("language")
        if lang and lang not in hidden_set:
            lang_counts[lang] += 1
    if not lang_counts:
        for r in repos:
            lang = r.get("language")
            if lang and lang not in hidden_set:
                lang_counts[lang] += 1

    total = sum(lang_counts.values()) or 1
    return [
        LanguageData(
            language=lang,
            percentage=round(count / total * 100, 1),
            loc=count,
        )
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])
    ]


def compute_streaks(github_data: dict, stored: dict | None) -> StreakData:
    """
    Compute the user's current and longest contribution streaks.

    Current streak: starts at today if today has contributions; else at
    yesterday if yesterday has contributions (1-day grace for end-of-UTC).
    Walks backward while consecutive days are all active.

    Max streak: scans the contribution window for the longest consecutive run,
    then merges with `stored["max_streak"]`. The greater value wins; when the
    stored value wins, its start/end dates are preserved.

    Args:
        github_data: Raw fetcher payload; reads "commits" as a list of
            {"date": "YYYY-MM-DD", "count": N}. Zero-count entries are ignored.
        stored: Optional dict from db.get_user_streak(username). None on first
            observation.
    """
    entries = github_data.get("commits") or []
    active = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        d = e.get("date")
        n = e.get("count") or 0
        if d and n > 0:
            active.add(d)

    stored = stored or {}
    prior_max       = int(stored.get("max_streak", 0) or 0)
    prior_max_start = stored.get("max_start", "") or ""
    prior_max_end   = stored.get("max_end", "") or ""
    stored_last     = stored.get("last_active_date", "") or ""

    if not active:
        return StreakData(
            current=0,
            max=prior_max,
            current_start="",
            last_active_date=stored_last,
            max_start=prior_max_start,
            max_end=prior_max_end,
        )

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    if today.isoformat() in active:
        cursor = today
    elif yesterday.isoformat() in active:
        cursor = yesterday
    else:
        cursor = None

    current = 0
    current_start = ""
    if cursor is not None:
        start = cursor
        while start.isoformat() in active:
            current += 1
            start -= timedelta(days=1)
        current_start = (start + timedelta(days=1)).isoformat()

    sorted_dates = sorted(active)
    from datetime import date as _date
    max_len = 0
    max_start_iso = ""
    max_end_iso = ""
    run_start = sorted_dates[0]
    run_len = 1
    prev = _date.fromisoformat(run_start)
    for ds in sorted_dates[1:]:
        cur = _date.fromisoformat(ds)
        if (cur - prev).days == 1:
            run_len += 1
        else:
            if run_len > max_len:
                max_len = run_len
                max_start_iso = run_start
                max_end_iso = prev.isoformat()
            run_start = ds
            run_len = 1
        prev = cur
    if run_len > max_len:
        max_len = run_len
        max_start_iso = run_start
        max_end_iso = prev.isoformat()

    if max_len > prior_max:
        merged_max = max_len
        merged_start = max_start_iso
        merged_end = max_end_iso
    else:
        merged_max = prior_max
        merged_start = prior_max_start
        merged_end = prior_max_end

    last_active = sorted_dates[-1]

    return StreakData(
        current=current,
        max=merged_max,
        current_start=current_start,
        last_active_date=last_active,
        max_start=merged_start,
        max_end=merged_end,
    )


def generate_widgets_from_github(
    github_data: dict,
    theme: str = "dark",
    custom_tags: list[str] = None,
    hidden_languages: list[str] = None,
    enabled: list[str] = None,
    widget_settings: dict[str, dict] | None = None,
    achievements: list[dict] | None = None,
    stored_streak: dict | None = None,
) -> dict[str, str]:
    """
    Takes raw GitHub API data and returns rendered SVG strings
    for each widget type.

    Args:
        github_data: GitHub profile data
        theme: Color theme name
        custom_tags: Optional list of custom tags to add to the grade widget
        hidden_languages: Optional list of languages to exclude from stats
        enabled: Optional list of widget keys to generate; others are skipped.
            Defaults to ENABLED_WIDGETS from config.
        widget_settings: Optional per-widget settings dict, keyed by widget name.
            Each value is a dict of settings for that widget's renderer.
        stored_streak: Optional dict from db.get_user_streak(username); carries
            the all-time longest streak forward across refreshes.
    """
    from .config import ENABLED_WIDGETS

    if enabled is None:
        enabled = ENABLED_WIDGETS
    enabled_set = set(enabled)
    ws = widget_settings or {}

    widgets: dict[str, str] = {}

    if "grade" in enabled_set:
        grade = compute_grade(github_data, custom_tags=custom_tags)
        widgets["grade"] = render_grade_widget(grade, theme, settings=ws.get("grade"))

    if "impact" in enabled_set:
        impact = compute_impact_timeline(github_data)
        widgets["impact"] = render_impact_widget(impact, theme, settings=ws.get("impact"))

    if "collaborators" in enabled_set:
        collabs = compute_collaborators(github_data)
        widgets["collaborators"] = render_collaborators_widget(collabs, theme, settings=ws.get("collaborators"))

    if "focus" in enabled_set:
        focus = compute_focus(github_data, hidden_languages=hidden_languages)
        widgets["focus"] = render_focus_widget(focus, theme, period="1y", settings=ws.get("focus"))

    if "languages" in enabled_set:
        languages = compute_languages(github_data, hidden_languages=hidden_languages)
        widgets["languages"] = render_languages_widget(languages, theme, settings=ws.get("languages"))

    if "streaks" in enabled_set:
        streak = compute_streaks(github_data, stored_streak)
        widgets["streaks"] = render_streaks_widget(streak, theme, settings=ws.get("streaks"))

    if "achievements" in enabled_set:
        # User-authored content — no GitHub data involved.
        raw = [a for a in (achievements or []) if (a.get("title") or "").strip()]
        items = [
            AchievementData(
                title=a.get("title", ""),
                subtitle=a.get("subtitle", ""),
                event_date=a.get("event_date", ""),
                icon=a.get("icon", "trophy"),
            )
            for a in raw
        ]
        if items:
            widgets["achievements"] = render_achievements_widget(items, theme, settings=ws.get("achievements"))

    return widgets
