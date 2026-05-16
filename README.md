# 🎬 LACC Cinema & TV Ranked Choice Voting System

Ranked Choice Voting for student film screenings at Los Angeles City College — Cinema & Television Department.

Built for two use cases:
- **Best of Semester** showcases — vote on films from the current term
- **Film Festivals** — submissions spanning multiple semesters, with full metadata context per film

Self-hosted, Docker-based. No student login required to vote.

---

## Features

- **Multiple independent polls** — create a named poll for each event, on demand
- **Step-by-step ballot wizard** — students pick their favorite, then their second, then their third... one question at a time. Clean, mobile-first, no confusion
- **Cookie-based deduplication** — one vote per browser, no IP tracking (school WiFi friendly)
- **Film metadata with color-coded pill chips** — class, professor, semester, and genre displayed on each ballot card
- **Multi-genre support** — comma-separated in CSV, renders as individual chips
- **CSV import** — upload your film list in one shot with a downloadable template
- **Upload order preserved** — films appear on the ballot in the order they were in the CSV
- **Configurable top-N picks** — set how many picks voters make per poll (default: 5)
- **Full IRV tabulation** — instant-runoff voting with round-by-round breakdown
- **1st–5th place standings** — derived from elimination order, shown with medal rankings
- **Admin-only results** — IRV results only visible to you until you choose to reveal them
- **Public results page** — toggle on when you're ready, designed to display on a projector at the event
- **Collapsible round breakdown** on the public results page — clean by default, expandable for transparency

---

## How Voting Works (IRV)

Students submit their ballot once — ranking their top N films in order. That's it, they're done.

When you close the poll, the app runs **Instant-Runoff Voting** automatically:

1. Count everyone's 1st pick
2. Eliminate the film with the fewest votes
3. Ballots that picked the eliminated film transfer to those voters' next choice
4. Repeat until one film has more than 50% of active votes

The winner is the film with the broadest genuine support — not just the most first-place votes. Used by the Academy Awards, Maine, Alaska, NYC, and many others.

---

## Class Color Codes

| Course | Color |
|---|---|
| Cinema 002 — Intro Production & Storytelling | 🟢 Green |
| Cinema 010 — Intro to Directing | 🔵 Blue |
| Cinema 012 — Advanced Directing | 🟣 Purple |
| Cinema 033 — Advanced Production | 🟡 Amber/Gold |
| Any other class | Neutral fallback |

---

## Stack

| Component | Technology |
|---|---|
| App | Python / Flask + Gunicorn |
| Database | PostgreSQL 16 |
| Container | Docker + Docker Compose |
| Image registry | GitHub Container Registry (GHCR) |
| Font | Public Sans (Google Fonts) |

---

## Deployment via Dockge

**Compose URL:**
```
https://raw.githubusercontent.com/lovelacecreativeco/lacc-film-rcv/main/compose.yaml
```

Paste into Dockge's "Add Stack" field, then set these environment variables:

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Random secret for Flask sessions | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DB_PASSWORD` | PostgreSQL password | `a-strong-password` |
| `ADMIN_PASSWORD` | Password for `/admin` | `your-admin-password` |
| `APP_PORT` | Host port to expose (optional) | `5000` (default) |

---

## Manual Docker Compose

```bash
git clone https://github.com/lovelacecreativeco/lacc-film-rcv.git
cd lacc-film-rcv
cp .env.example .env
# Edit .env and fill in SECRET_KEY, DB_PASSWORD, ADMIN_PASSWORD
docker compose up -d
```

App available at `http://localhost:5000`.

---

## Nginx Proxy Manager

Add a proxy host pointing to port `5000` (or your `APP_PORT`). NPM passes `X-Forwarded-For` by default — no extra configuration needed.

---

## Admin Workflow

### Setting up a poll

1. Go to `/admin` and log in
2. Click **Create Poll** — give it a name (e.g. `Spring 2026 Film Festival`) and set the top-N picks (default 5)
3. Download the CSV template and fill in your film list
4. Upload the CSV — films appear instantly with all their metadata chips
5. Click **Open Poll** and share the URL with students: `/poll/3`

### On voting night

6. Students visit the URL and are walked through the wizard step by step — picking their favorite, then second favorite, etc.
7. When everyone has voted, click **Close Poll**
8. IRV results appear immediately on your admin page — winner, 1st–5th place standings, round-by-round breakdown

### Revealing results (e.g. at a screening or festival)

9. Click **🎉 Reveal Results to Public** — the public results page goes live
10. Share or project `/poll/3/results` — students see the winner, standings, and can optionally expand the full round-by-round math

To hide the results again, click the same button to toggle off.

---

## CSV Format

Download the template from the admin panel, or match this structure:

```csv
title,student,genre,class,professor,semester
My Short Film,Jane Smith,"Drama, Thriller",Cinema 033,Prof. Garcia,Fall 2025
Another Story,Alex Johnson,Documentary,Cinema 002,Prof. Kim,Fall 2025
The Final Frame,Sam Lee,"Horror, Sci-Fi",Cinema 012,Prof. Patel,Spring 2026
Festival Entry,Casey Brown,Comedy,Cinema 010,Prof. Nguyen,Spring 2024
```

Only `title` is required. All other columns are optional and appear as pill chips on the ballot. Multiple genres can be comma-separated. Films appear on the ballot in the order they appear in the CSV.

---

## Database Migrations

If upgrading from an earlier version, run these against your existing database as needed:

```sql
-- Rename director to student (v2 to v3)
ALTER TABLE film RENAME COLUMN director TO student;

-- Add genre column
ALTER TABLE film ADD COLUMN IF NOT EXISTS genre VARCHAR(100) DEFAULT '';

-- Add sort_order column
ALTER TABLE film ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;

-- Add top_n to polls
ALTER TABLE poll ADD COLUMN IF NOT EXISTS top_n INTEGER DEFAULT 5;

-- Add results_visible to polls
ALTER TABLE poll ADD COLUMN IF NOT EXISTS results_visible BOOLEAN DEFAULT FALSE;
```

Run via Dockge's db container terminal:
```bash
psql -U rcv -d rcvdb -c "ALTER TABLE ..."
```

Or from your Docker host:
```bash
docker exec -it rcv-film-db-1 psql -U rcv -d rcvdb -c "ALTER TABLE ..."
```

---

## Updating

GitHub Actions automatically rebuilds the Docker image on every push to `main`. To deploy an update:

1. Push changes to `main`
2. In Dockge, click **Pull & Restart** on the stack

The `pgdata` volume persists across restarts — no data is lost.

---

## Full Reset

To wipe everything and start fresh:

```bash
docker compose down -v   # -v removes the pgdata volume
docker compose up -d
```

To clear just the ballots for a specific poll without losing films, use **Clear All Ballots** in the admin panel danger zone.

---

## URL Reference

| URL | Who | Description |
|---|---|---|
| `/` | Everyone | Lists all open polls, or redirects if only one is open |
| `/poll/<id>` | Everyone | Ballot for a specific poll |
| `/poll/<id>/results` | Everyone (when toggled on) | Public results page for projector display |
| `/admin` | Admin | List of all polls |
| `/admin/polls/<id>` | Admin | Manage a poll, view IRV results |

---

## Local Development

```bash
cd app
pip install -r requirements.txt
# Set env vars, point DATABASE_URL at a local postgres instance
python app.py
```

---

*Built for LACC Cinema & Television Department — Equipment Room / Instructional Media*
*GitHub: [lovelacecreativeco/lacc-film-rcv](https://github.com/lovelacecreativeco/lacc-film-rcv)*
