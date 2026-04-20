# github-readme-stats

[![tests](https://github.com/ShayManor/github-readme-stats/actions/workflows/tests.yml/badge.svg)](https://github.com/ShayManor/github-readme-stats/actions/workflows/tests.yml)
[![build and deploy](https://github.com/ShayManor/github-readme-stats/actions/workflows/deploy.yml/badge.svg)](https://github.com/ShayManor/github-readme-stats/actions/workflows/deploy.yml)

A single SVG widget you drop into your GitHub profile README. It scores
your account, charts your contribution timeline, highlights your top
collaborators, breaks down your languages, tracks your commit streaks,
and earns you tags like `Backend`, `ML`, or `Founder #42`.

```md
![my stats](https://gh-stats.com/YOUR_USERNAME)
```

![hero widget](https://gh-stats.com/ShayManor)

<details>
<summary>Table of contents (click to show)</summary>

- [Quick start](#quick-start)
- [The composite widget](#the-composite-widget)
- [Individual widgets](#individual-widgets)
  - [Grade](#grade)
  - [Impact timeline](#impact-timeline)
  - [Streaks](#streaks)
  - [Top collaborators](#top-collaborators)
  - [Recent focus](#recent-focus)
  - [Languages](#languages)
  - [Achievements](#achievements)
- [Themes](#themes)
- [Customization via query parameters](#customization-via-query-parameters)
- [Refreshing your data](#refreshing-your-data)
- [Status states](#status-states)
- [Self-hosting](#self-hosting)
- [Running tests](#running-tests)
- [FAQ](#faq)

</details>

---

## Quick start

1. Open <https://gh-stats.com/> in a browser.
2. **Sign in with GitHub** — this enrolls your username and makes you the
   owner of the widget. The editor (Workshop) is only accessible to the
   signed-in owner.
3. Pick a theme, reorder widgets, add custom tags and achievements.
4. Click **Generate** — the SVG is built on the server and cached.
5. Copy the one-liner into your profile README:

   ```md
   ![my stats](https://gh-stats.com/YOUR_USERNAME)
   ```

That's it. A 15-minute refresh cron picks up new GitHub activity, so the
image stays current on its own.

> [!NOTE]
> The image URL is stable. Once it's in your README, you can change
> themes, tags, or widget order in the Workshop without ever touching
> the markdown again.

---

## The composite widget

The default URL returns a single composed card with every enabled widget
stacked in your chosen order.

Endpoint: `https://gh-stats.com/<username>`

```md
![stats](https://gh-stats.com/anuraghazra)
```

![composite example](https://gh-stats.com/anuraghazra)

> [!WARNING]
> Only public GitHub activity is counted. Private commits, private
> repos, and organization-restricted contributions are not visible to
> the fetcher. This applies even on self-hosted deployments — the PAT
> only sees what GitHub's public GraphQL/REST endpoints expose.

---

## Individual widgets

Don't want the full stack? Every widget is independently addressable at
`https://gh-stats.com/<username>/<widget>.svg`:

```md
![grade](https://gh-stats.com/YOUR_USERNAME/grade.svg)
![impact](https://gh-stats.com/YOUR_USERNAME/impact.svg)
![streaks](https://gh-stats.com/YOUR_USERNAME/streaks.svg)
![collaborators](https://gh-stats.com/YOUR_USERNAME/collaborators.svg)
![focus](https://gh-stats.com/YOUR_USERNAME/focus.svg)
![languages](https://gh-stats.com/YOUR_USERNAME/languages.svg)
![achievements](https://gh-stats.com/YOUR_USERNAME/achievements.svg)
```

Put two side-by-side with an HTML table (GitHub strips inline CSS, so a
table is the only reliable way):

```html
<table><tr>
  <td><img src="https://gh-stats.com/YOUR_USERNAME/grade.svg"/></td>
  <td><img src="https://gh-stats.com/YOUR_USERNAME/languages.svg"/></td>
</tr></table>
```

### Grade

Overall score (0–100), letter grade (S / A / B / C / D / F), and your
top role tags. The grade is a weighted blend of commit volume, review
activity, recent authorship, and language breadth — see
`generator/src/scoring.py` for the exact formula.

```md
![grade](https://gh-stats.com/YOUR_USERNAME/grade.svg?grade.max_tags=6)
```

### Impact timeline

A smooth contribution curve over the last 6 months, drawn against a
faint grid. Nice on its own, or sitting above a languages card.

```md
![impact](https://gh-stats.com/YOUR_USERNAME/impact.svg?impact.line_color=%23a78bfa)
```

### Streaks

Current and longest contribution streak, with a small spark chart.

```md
![streaks](https://gh-stats.com/YOUR_USERNAME/streaks.svg?streaks.color=%233fb950)
```

### Top collaborators

Avatars, shared-repo count, and commit bars for the people you work
with most. We filter out huge OSS projects (configurable via
`COLLABORATOR_MAX_REPO_SIZE`) so your drive-by PR to `react` doesn't
put the React team on your card.

```md
![collab](https://gh-stats.com/YOUR_USERNAME/collaborators.svg?collaborators.max_count=5)
```

### Recent focus

What you've actually been working on lately, grouped by topic/language
cluster.

```md
![focus](https://gh-stats.com/YOUR_USERNAME/focus.svg?focus.max_categories=5)
```

### Languages

Your language mix, weighted by bytes in **repos you authored** (forks
where you haven't contributed meaningfully are ignored). Hide noise
like `HTML` or `Makefile` with the `hide` parameter.

```md
![langs](https://gh-stats.com/YOUR_USERNAME/languages.svg?hide=HTML,CSS,Makefile)
```

### Achievements

Up to 10 hand-entered lines — hackathons, talks, awards, certifications.
Each line has an icon (`trophy`, `medal`, `star`, `hackathon`), a
title, a subtitle, and an optional date.

```md
![ach](https://gh-stats.com/YOUR_USERNAME/achievements.svg)
```

---

## Themes

Pass `?theme=<name>` or pick one in the Workshop. Five built-ins:

| Theme | Tone |
|---|---|
| `midnight` *(default)* | dark, soft blue accents |
| `onyx` | deep black, neon violet |
| `nord` | muted pastel on slate |
| `clean` | white, understated |
| `paper` | warm off-white |

```md
![onyx](https://gh-stats.com/YOUR_USERNAME?theme=onyx)
![nord](https://gh-stats.com/YOUR_USERNAME?theme=nord)
![clean](https://gh-stats.com/YOUR_USERNAME?theme=clean)
![paper](https://gh-stats.com/YOUR_USERNAME?theme=paper)
```

### Dark / light auto-switching

Use GitHub's built-in theme context suffixes to serve a different image
to viewers on dark vs. light GitHub:

```md
![dark](https://gh-stats.com/YOUR_USERNAME?theme=onyx#gh-dark-mode-only)
![light](https://gh-stats.com/YOUR_USERNAME?theme=clean#gh-light-mode-only)
```

Or with `<picture>` for precise `prefers-color-scheme` control:

```html
<picture>
  <source srcset="https://gh-stats.com/YOUR_USERNAME?theme=onyx"
          media="(prefers-color-scheme: dark)" />
  <source srcset="https://gh-stats.com/YOUR_USERNAME?theme=clean"
          media="(prefers-color-scheme: light)" />
  <img src="https://gh-stats.com/YOUR_USERNAME" />
</picture>
```

---

## Customization via query parameters

Every widget URL accepts query parameters. They let you override the
owner's saved settings on a per-embed basis **without re-enrolling or
signing in** — useful when someone else wants to embed your widget
with different options. Nothing is persisted; the owner's widget is
unaffected.

### Common parameters

| Parameter | Description | Type | Example |
|---|---|---|---|
| `theme` | Built-in theme name. | enum | `?theme=onyx` |
| `widgets` | Which widgets to render (composite only). | csv | `?widgets=grade,languages` |
| `order` | Render order (composite only). | csv | `?order=grade,streaks,impact` |
| `hide` | Languages to exclude from the languages widget. | csv | `?hide=HTML,CSS,Makefile` |
| `tags` | Extra custom role tags to merge into the grade widget. | csv | `?tags=ML,Systems` |
| `ach` | Achievements list as url-safe base64(json). | string | see below |

> [!NOTE]
> Values with special characters must be URL-encoded. `#a78bfa` becomes
> `%23a78bfa`; `Jupyter Notebook` becomes `Jupyter%20Notebook`.

### Per-widget parameters

Use dot notation: `<widget>.<key>=<value>`.

| Parameter | Description | Type | Default |
|---|---|---|---|
| `grade.max_tags` | Max role tags shown on the grade card (1–20). | int | all tags |
| `impact.line_color` | Accent color for the contribution curve. | hex color | theme accent |
| `streaks.color` | Accent color for the streak bars. | hex color | theme green |
| `collaborators.max_count` | Max collaborators shown (1–10). | int | `5` |
| `collaborators.bar_color` | Accent color for the commit bars. | hex color | theme accent |
| `focus.max_categories` | Max focus clusters shown (1–10). | int | `6` |
| `languages.max_languages` | Max languages shown (1–10). | int | `5` |
| `achievements.max_items` | Max achievement rows shown (1–10). | int | `5` |

Example combining several overrides:

```md
![stats](https://gh-stats.com/YOUR_USERNAME?theme=onyx&widgets=grade,streaks,languages&order=grade,streaks,languages&hide=HTML,CSS&grade.max_tags=4&streaks.color=%23a78bfa)
```

### Auto-awarded tags

Some tags on the grade card are earned from real activity — no query
parameter will add them if you haven't earned them:

- `Founder #N` — one of the first N users to enroll. Your number is
  fixed at enrollment and never changes.
- Role tags like `Backend`, `Frontend`, `ML`, `Mobile`, `DevOps`,
  `Cloud`, `Systems`, `Database`, `Security` — derived from your
  language mix and repo topics. The mapping lives in
  `generator/src/config.py` (`TAG_LANGUAGE_MAP`, `TAG_TOPIC_MAP`).

---

## Refreshing your data

The refresh cron re-pulls GitHub data every **15 minutes**, so new
commits typically appear in your widget within that window. GitHub's
image CDN may add another minute or two of staleness on top.

If you need an immediate update (e.g. right after merging something
big), click **Refresh now** in the Workshop. This is a **one-shot per
account** — use it when it matters.

---

## Status states

The SVG endpoint advertises its state via the `X-Widget-Status`
response header, and the edge cache uses it to decide whether to cache:

| Status | Meaning | What the viewer sees |
|---|---|---|
| `ready` | Built and cached | the real widget |
| `building` | Enrolled, first render in progress | a placeholder card |
| `rate_limited` | Daily enrollment cap hit | a placeholder card |
| `not_found` | GitHub username doesn't exist | a 404-style card |

GitHub caches images aggressively; a just-enrolled widget may show the
placeholder for a minute or two before the real image propagates. This
is normal — no action needed on your side.

---

## Self-hosting

If you want your own instance, it runs as three Python services plus a
Vite+React SPA served by the generator. You'll need a GitHub Personal
Access Token (classic, `read:user` + `repo:public_repo` is enough) and,
for OAuth-based enrollment, a GitHub OAuth App.

```bash
# 1) fetcher — owns the PAT, talks to GitHub                  (port 5001)
cd fetcher && pip install -r requirements.txt
FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=<your-pat> python -m src.api &

# 2) generator — API + worker + refresh cron                  (port 5002)
cd ../generator && pip install -r requirements.txt
export FETCHER_URL=http://localhost:5001
export FETCHER_INTERNAL_TOKEN=dev
export GH_OAUTH_CLIENT_ID=<client-id>
export GH_OAUTH_CLIENT_SECRET=<client-secret>
python -m src.api   &
python -m src.worker &
python -m src.cron   &

# 3) edge — cache-first SVG proxy (put this behind your domain) (port 5003)
cd ../edge && pip install -r requirements.txt
GENERATOR_URL=http://localhost:5002 python -m src.api &

# 4) frontend (dev only — production builds are baked into the generator image)
cd ../generator/frontend && npm install && npm run dev
```

Each service is independent: a Dockerfile, `requirements.txt`, and
`pytest.ini` sit in its directory. The generator image bundles the
pre-built frontend, so a production deploy is `edge → generator →
fetcher` with one domain pointed at edge.

### Capacity knobs

Sensible defaults out of the box; all overridable via env:

| Env | Default | What it bounds |
|---|---|---|
| `GENERATE_CONCURRENCY` | `2` | Simultaneous SVG renders |
| `PREFETCH_MAX_WORKERS` | `2` | Background prefetch threads |
| `PENDING_JOB_QUEUE_CAP` | `200` | Build-queue depth before new enrolls 429 |
| `ENROLLMENT_DAILY_CAP` | `50` | New users per day |
| `RATE_LIMIT_READ_MAX` | `3000` per 60s | Per-IP README embeds |
| `RATE_LIMIT_MUTATE_MAX` | `120` per 60s | Per-IP settings edits / generates |
| `RATE_LIMIT_ENROLL_MAX` | `60` per 300s | Per-IP new enrollments |
| `EDGE_RATE_LIMIT_MAX` | `3000` per 60s | Per-IP at the edge |

### Required env for OAuth

| Env | Description |
|---|---|
| `GH_OAUTH_CLIENT_ID` | GitHub OAuth App client ID |
| `GH_OAUTH_CLIENT_SECRET` | GitHub OAuth App client secret |
| `GH_OAUTH_REDIRECT_URI` | Callback URL, e.g. `https://gh-stats.com/api/auth/github/callback` |
| `GENERATOR_SECRET_KEY` | Flask session signing key (`python -c 'import secrets;print(secrets.token_hex(32))'`) |
| `ALLOWED_ORIGINS` | Comma-separated origin allow-list for mutate routes |

---

## Running tests

Each service is self-contained:

```bash
(cd fetcher && pytest) && (cd generator && pytest) && (cd edge && pytest)
```

---

## FAQ

**Can I use a private GitHub account?**
No. The fetcher only reads public activity. Private repos, private
commit counts, and org-restricted contributions are never included —
even on a self-hosted instance, since the public GitHub API doesn't
expose them.

**How fresh is the data?**
Every 15 minutes via the refresh cron. You can also click **Refresh
now** in the Workshop once per account for an immediate update.

**How do I edit my widget?**
Sign in with GitHub at <https://gh-stats.com/>. Only the GitHub account
that owns the username can edit that widget's settings. There is no
other edit path — the Workshop's mutate routes require both a valid
session cookie and a matching login.

**Someone else's username is already showing on the site — can I claim it?**
Yes. Enrollment happens implicitly on first GitHub sign-in: the first
time the owner of a username signs in, their settings row is created
(or taken over, if it was auto-enrolled by a previous viewer). No
manual claim step is needed.

**Can I change the widget without re-embedding?**
Yes. The image URL is stable. Edit settings in the Workshop, click
**Generate**, and the next fetch serves the new version. GitHub's
image cache may delay propagation by a few minutes.

**Can I embed someone else's widget with my own theme / filters?**
Yes — use [query parameters](#customization-via-query-parameters). The
owner's stored settings are unaffected; the override render is
computed on demand and cached briefly.

**I'm getting a placeholder card. What's wrong?**
Check the `X-Widget-Status` header on the response (`curl -I
https://gh-stats.com/<username>`). `building` means first render is in
progress — wait a minute. `rate_limited` means the daily enrollment
cap was hit — try tomorrow. `not_found` means GitHub doesn't know
that username.

**Why does my `Languages` card look wrong?**
The languages widget only counts repos you authored, weighted by
bytes. Forks where you haven't made enough commits are excluded (see
`FORK_MIN_COMMITS`). Add `?hide=HTML,CSS,Makefile` if stock-generated
files are dominating the breakdown.

**Does the public instance work for high-traffic profiles?**
It's best-effort. The public instance at `gh-stats.com` runs on a
single mini PC, and the capacity knobs above are tuned for that. If
your profile gets heavy traffic, self-host — the edge cache in front
of the generator scales the read path almost for free.
