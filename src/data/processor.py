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

    repo_count = min(len(repos), 50)
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    forks = sum(r.get("forks_count", 0) for r in repos)
    followers = user.get("followers", 0)
    commits = sum(
        len(ev.get("payload", {}).get("commits", []))
        for ev in events if ev.get("type") == "PushEvent"
    )
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
    """Aggregate events into weekly impact data."""
    events = github_data["events"]
    weekly = defaultdict(lambda: {"commits": 0})

    for ev in events:
        if ev.get("type") == "PushEvent":
            created = ev.get("created_at", "")[:10]
            if created:
                dt = datetime.fromisoformat(created)
                week_start = (dt - timedelta(days=dt.weekday())).isoformat()[:10]
                commits = len(ev.get("payload", {}).get("commits", []))
                weekly[week_start]["commits"] += commits

    weeks = []
    for ws in sorted(weekly.keys()):
        d = weekly[ws]
        weeks.append(ImpactWeek(week_start=ws, commits=d["commits"]))

    return weeks


def compute_collaborators(github_data: dict) -> list[CollaboratorData]:
    """Find top collaborators from events."""
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
    )[:5]:
        collabs.append(
            CollaboratorData(
                username=username,
                shared_repos=len(stats["repos"]),
                shared_commits=stats["commits"],
            )
        )

    return collabs


def compute_focus(github_data: dict) -> list[FocusCategory]:
    """Classify commits into focus categories."""
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
