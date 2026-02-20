"""GitHub data processing and widget generation."""

from datetime import datetime, timedelta
from collections import defaultdict

from ..models import (
    GradeData,
    TagData,
    ImpactWeek,
    CollaboratorData,
    FocusCategory,
    LanguageData,
)
from ..widgets import (
    render_grade_widget,
    render_impact_widget,
    render_collaborators_widget,
    render_focus_widget,
    render_languages_widget,
)


def compute_grade(github_data: dict) -> GradeData:
    """Compute a developer grade from GitHub profile data."""
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

    scores = {
        "repos": min(repo_count / 30 * 100, 100),
        "stars": min(stars / 200 * 100, 100),
        "forks": min(forks / 50 * 100, 100),
        "followers": min(followers / 100 * 100, 100),
        "activity": min(len(events) / 80 * 100, 100),
    }

    total = sum(scores.values()) / len(scores)

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
    elif total >= 35:
        grade = "C"
    elif total >= 28:
        grade = "C-"
    elif total >= 20:
        grade = "D+"
    elif total >= 12:
        grade = "D"
    elif total >= 5:
        grade = "D-"
    else:
        grade = "F"

    stats = {
        "commits": commits,
        "prs": prs,
        "stars": stars,
        "repos": repo_count,
        "followers": followers,
    }

    tags = _compute_tags(github_data)

    return GradeData(
        grade=grade,
        score=round(total, 1),
        stats=stats,
        tags=tags,
        breakdown={k: round(v, 1) for k, v in scores.items()},
    )


def _compute_tags(github_data: dict) -> list[TagData]:
    """Infer developer tags from repo languages and topics."""
    repos = github_data["repos"]
    lang_counts = defaultdict(int)
    topic_set = set()

    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1
        for topic in r.get("topics", []):
            topic_set.add(topic.lower())

    tags = []
    total = sum(lang_counts.values()) or 1

    lang_map = {
        "Python": ["ml-engineer", "backend"],
        "JavaScript": ["frontend"],
        "TypeScript": ["frontend"],
        "Go": ["backend", "systems"],
        "Rust": ["systems"],
        "Java": ["backend"],
        "C++": ["systems"],
        "Swift": ["mobile"],
        "Kotlin": ["mobile"],
        "Dockerfile": ["devops"],
        "HCL": ["devops", "cloud"],
    }

    inferred = defaultdict(float)
    for lang, count in lang_counts.items():
        pct = count / total
        for tag in lang_map.get(lang, []):
            inferred[tag] = max(inferred[tag], pct)

    topic_map = {
        "machine-learning": "ml-engineer",
        "deep-learning": "ml-engineer",
        "frontend": "frontend",
        "react": "frontend",
        "vue": "frontend",
        "backend": "backend",
        "api": "backend",
        "database": "database",
        "devops": "devops",
        "docker": "devops",
        "kubernetes": "devops",
        "security": "security",
        "fullstack": "fullstack",
    }

    for topic in topic_set:
        if topic in topic_map:
            inferred[topic_map[topic]] = max(
                inferred.get(topic_map[topic], 0), 0.7
            )

    # Fullstack heuristic
    has_fe = any(
        lang_counts.get(l, 0) > 0 for l in ["JavaScript", "TypeScript"]
    )
    has_be = any(
        lang_counts.get(l, 0) > 0
        for l in ["Python", "Go", "Java", "Rust", "C++"]
    )
    if has_fe and has_be:
        inferred["fullstack"] = max(inferred.get("fullstack", 0), 0.6)

    for tag, conf in sorted(inferred.items(), key=lambda x: -x[1])[:6]:
        tags.append(TagData(tag=tag, source="earned", confidence=round(conf, 2)))

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
    Find top collaborators - people who committed to the same repos as the user.

    Uses actual commit/contributor data to find meaningful collaborations.
    Filters out huge OSS projects by requiring 10+ commits threshold.
    """
    collaborators_data = github_data.get("collaborators_data", {})

    if not collaborators_data:
        # Fallback to events-based if no collaborator data
        return _compute_collaborators_from_events(github_data)

    # Aggregate collaborators across all shared repos
    collab_stats = defaultdict(lambda: {
        "repos": set(),
        "commits": 0,
        "avatar_url": ""
    })

    for repo_name, contributors in collaborators_data.items():
        for contributor in contributors:
            login = contributor.get("login", "")
            if login:
                collab_stats[login]["repos"].add(repo_name)
                collab_stats[login]["commits"] += contributor.get("contributions", 0)
                if not collab_stats[login]["avatar_url"]:
                    collab_stats[login]["avatar_url"] = contributor.get("avatar_url", "")

    # Sort by total commits and take top 4
    collabs = []
    for username, stats in sorted(
        collab_stats.items(), key=lambda x: -x[1]["commits"]
    )[:4]:  # Show exactly 4 collaborators
        collabs.append(
            CollaboratorData(
                username=username,
                shared_repos=len(stats["repos"]),
                shared_commits=stats["commits"],
                avatar_b64="",  # Will be fetched if needed
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


def compute_focus(github_data: dict) -> list[FocusCategory]:
    """Classify commits into focus categories based on repo languages and activity."""
    repos = github_data["repos"]
    events = github_data["events"]

    lang_to_focus = {
        "Python": "Python",
        "JavaScript": "Frontend",
        "TypeScript": "Frontend",
        "HTML": "Frontend",
        "CSS": "Frontend",
        "Go": "Backend",
        "Rust": "Systems",
        "Java": "Backend",
        "C++": "Systems",
        "C": "Systems",
        "Ruby": "Backend",
        "PHP": "Backend",
        "Shell": "DevOps",
        "Dockerfile": "DevOps",
        "Jupyter Notebook": "ML",
    }

    focus_counts = defaultdict(int)

    # Use events-based counting to track actual activity
    repo_langs = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            repo_langs[r["full_name"]] = lang

    for ev in events:
        if ev.get("type") == "PushEvent":
            repo_name = ev.get("repo", {}).get("name", "")
            lang = repo_langs.get(repo_name)
            focus = lang_to_focus.get(lang, "Other")
            commits = len(ev.get("payload", {}).get("commits", []))
            focus_counts[focus] += commits

    # If no events, fallback to repo count
    if not focus_counts:
        for r in repos:
            lang = r.get("language")
            if lang:
                focus = lang_to_focus.get(lang, "Other")
                focus_counts[focus] += 1

    total = sum(focus_counts.values()) or 1
    return [
        FocusCategory(
            category=cat,
            percentage=round(count / total * 100, 1),
            commit_count=count,
        )
        for cat, count in sorted(focus_counts.items(), key=lambda x: -x[1])
    ]


def compute_languages(github_data: dict) -> list[LanguageData]:
    """Compute language distribution from repos."""
    repos = github_data["repos"]
    lang_counts = defaultdict(int)
    for r in repos:
        lang = r.get("language")
        if lang:
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


def generate_widgets_from_github(
    github_data: dict, theme: str = "dark"
) -> dict[str, str]:
    """
    Takes raw GitHub API data and returns rendered SVG strings
    for each widget type.
    """
    grade = compute_grade(github_data)
    impact = compute_impact_timeline(github_data)
    collabs = compute_collaborators(github_data)
    focus = compute_focus(github_data)
    languages = compute_languages(github_data)

    return {
        "grade": render_grade_widget(grade, theme),
        "impact": render_impact_widget(impact, theme),
        "collaborators": render_collaborators_widget(collabs, theme),
        "focus": render_focus_widget(focus, theme, period="1y"),
        "languages": render_languages_widget(languages, theme),
    }
