# github-readme-stats

[![tests](https://github.com/ShayManor/github-readme-stats/actions/workflows/tests.yml/badge.svg)](https://github.com/ShayManor/github-readme-stats/actions/workflows/tests.yml)
[![build and deploy](https://github.com/ShayManor/github-readme-stats/actions/workflows/deploy.yml/badge.svg)](https://github.com/ShayManor/github-readme-stats/actions/workflows/deploy.yml)

A single SVG widget you drop into your GitHub profile README. It scores
your account, charts your contribution timeline, highlights your top
collaborators, breaks down your languages, and earns you tags like
`Backend`, `ML`, or `Founder #42`.

![hero widget](https://gh-stats.com/ShayManor)

---

## Get your widget in 30 seconds

1. Open `https://gh-stats.com/` in a browser.
2. Type your GitHub username and hit **Continue**.
3. Pick a theme, reorder widgets, add custom tags / achievements.
4. Click **Generate** — the SVG is built on the server and cached.
5. Copy the one-liner and paste it into your profile README:

   ```markdown
   ![my stats](https://gh-stats.com/YOUR_USERNAME)
   ```

That's it. Every push of GitHub activity is picked up by a 15-minute
refresh cron, so the image stays current without you doing anything.

---

## What's in the widget

| Widget | What it shows |
|---|---|
| **Grade** | Overall score (0–100) + letter grade + top tags |
| **Impact Timeline** | Smooth contribution curve over the last 6 months |
| **Top Collaborators** | Avatars + shared-repo + commit bars |
| **Recent Focus** | What you've actually been working on lately |
| **Languages** | Your language mix, weighted by active code |
| **Achievements** | Hand-entered credentials — hackathons, talks, awards |

Widgets are composed into a single card, or you can embed any one of
them on its own — see [Individual widgets](#individual-widgets).

---

## Themes

Pass `?theme=<name>` or pick in the Workshop. Five built-ins:

| Theme | Tone |
|---|---|
| `midnight` *(default)* | dark, soft blue accents |
| `onyx` | deep black, neon violet |
| `nord` | muted pastel on slate |
| `clean` | white, understated |
| `paper` | warm off-white |

```markdown
![my stats](https://gh-stats.com/YOUR_USERNAME?theme=onyx)
```

---

## Individual widgets

Don't want the full composite? Embed exactly one:

```markdown
![grade](https://gh-stats.com/YOUR_USERNAME/grade.svg)
![impact](https://gh-stats.com/YOUR_USERNAME/impact.svg)
![collaborators](https://gh-stats.com/YOUR_USERNAME/collaborators.svg)
![focus](https://gh-stats.com/YOUR_USERNAME/focus.svg)
![languages](https://gh-stats.com/YOUR_USERNAME/languages.svg)
![achievements](https://gh-stats.com/YOUR_USERNAME/achievements.svg)
```

Put two side-by-side with an HTML table:

```html
<table><tr>
  <td><img src="https://gh-stats.com/YOUR_USERNAME/grade.svg"/></td>
  <td><img src="https://gh-stats.com/YOUR_USERNAME/languages.svg"/></td>
</tr></table>
```

---

## Customization

Everything is editable from the Workshop UI — the settings are saved
against your username, so re-embedding picks them up automatically.

- **Custom tags** — add role labels like `ML`, `Systems`, `Cloud`. The
  grade widget will fit them into its tag cloud.
- **Hidden languages** — exclude languages you don't want counted
  (e.g. `HTML`, `CSS`, `Makefile`).
- **Widget colors** — per-widget accent overrides for the impact line
  and collaborator bars (hex, `#RRGGBB`).
- **Widget limits** — cap the number of tags, collaborators, or
  languages shown.
- **Achievements** — up to 10 hand-entered lines with icon
  (`trophy`, `medal`, `star`, `hackathon`), title, subtitle, and date.

**Auto-awarded tags** fire from real activity — no way to fake them:

- `Founder #N` — one of the first N enrolled users, with your number
- (plus anything your languages / topics map to: `Backend`, `Frontend`,
  `ML`, `Mobile`, `DevOps`, `Cloud`, …)

---

## Refreshing

Your data refreshes automatically every 15 minutes. If you just merged
something big and want it to show up immediately, click **Refresh now**
in the Workshop (one-shot per account; requires the edit token that was
issued to your browser on first visit).

---

## Status states

The SVG endpoint advertises its state via the `X-Widget-Status` header:

| Status | Meaning | Your README shows |
|---|---|---|
| `ready` | Built and cached | the real widget |
| `building` | Enrolled, first render in progress | a placeholder card |
| `rate_limited` | Daily enrollment cap hit | a placeholder card |
| `not_found` | GitHub username doesn't exist | a 404-style card |

GitHub caches the image aggressively; if a just-enrolled widget shows
the placeholder for a minute or two, that's expected.

---

## Self-hosting

If you want your own instance, it runs as three Docker services plus a
Vite-built React SPA served by the generator. You'll need a GitHub
Personal Access Token (classic, `read:user` + `repo:public_repo` is
enough).

```bash
# 1) fetcher — owns the PAT, talks to GitHub
(cd fetcher && pip install -r requirements.txt &&
 FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=<your-pat> python -m src.api) &

# 2) generator — API + worker + refresh cron
cd generator && pip install -r requirements.txt
FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.api &
FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.worker &
FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.cron &

# 3) edge — cache-first SVG proxy (this is what you put behind your domain)
(cd ../edge && pip install -r requirements.txt &&
 GENERATOR_URL=http://localhost:5002 python -m src.api) &

# 4) frontend (dev only — production builds are baked into the generator image)
cd ../generator/frontend && npm install && npm run dev
```

Per-service READMEs cover Docker, tests, and env vars:

- [`fetcher/`](./fetcher/README.md) — port 5001
- [`generator/`](./generator/README.md) — port 5002
- [`edge/`](./edge/README.md) — port 5003

The generator image serves both the API and the pre-built frontend, so
after deploying edge + generator + fetcher you can point a domain at
the edge and you're done.

### Capacity knobs

Sensible defaults; all overridable via env:

| Env | Default | What it bounds |
|---|---|---|
| `GENERATE_CONCURRENCY` | `2` | Simultaneous SVG renders |
| `PREFETCH_MAX_WORKERS` | `2` | Background prefetch threads |
| `PENDING_JOB_QUEUE_CAP` | `200` | Build queue depth before new enrolls 429 |
| `ENROLLMENT_DAILY_CAP` | `50` | New users per day |
| `RATE_LIMIT_READ_MAX` | `3000` per 60s | Per-IP README embeds |
| `RATE_LIMIT_MUTATE_MAX` | `120` per 60s | Per-IP settings edits / generates |
| `RATE_LIMIT_ENROLL_MAX` | `60` per 300s | Per-IP new enrollments |
| `EDGE_RATE_LIMIT_MAX` | `3000` per 60s | Per-IP at the edge |

---

## Running tests

```bash
(cd fetcher && pytest) && (cd generator && pytest) && (cd edge && pytest)
```

---

## FAQ

**Can I use a private GitHub account?**
No — the fetcher only sees public activity. Private repos and private
contribution counts aren't included.

**How fresh is the data?**
The refresh cron ticks every 15 minutes. You can also click **Refresh
now** in the Workshop once per account.

**Someone else already enrolled my username — can I edit it?**
The first browser to visit your username gets the edit token. If that
was you but you've lost the token (cleared localStorage, switched
browsers), there's no recovery path today — an OAuth-based reclaim
flow is on the roadmap.

**Can I change the widget without re-embedding?**
Yes. The image URL is stable. Edit settings in the Workshop, click
Generate, and the next time the image is fetched it's the new version
(GitHub's image cache may delay that by a few minutes).
