# 🎬 LACC Film RCV

Ranked Choice Voting for student film screenings at Los Angeles City College — Cinema & Television Department.

Built for two use cases:
- **Best of Semester** showcases — vote on films from the current term
- **Film Festivals** — submissions spanning multiple semesters, with full metadata context per film

Self-hosted, Docker-based, no student login required.

---

## Features

- **Multiple independent polls** — create a new poll for each event, on demand
- **Drag-to-rank ballot UI** — works on desktop and mobile
- **Cookie-based deduplication** — one vote per browser, no IP tracking (school wifi friendly)
- **Film metadata with color-coded pill chips** — class, professor, and semester displayed on each ballot card
- **CSV import** — upload a spreadsheet of films in one shot, with a downloadable template
- **Full IRV tabulation** — round-by-round bar chart breakdown, admin-only until you're ready
- **Admin panel** — create/open/close polls, manage films, view results

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

---

## Deployment via Dockge

**Compose URL:**
```
https://raw.githubusercontent.com/YOURUSERNAME/lacc-film-rcv/main/compose.yaml
```

Paste into Dockge's "Add Stack" field, then set these environment variables in Dockge's env editor:

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Random secret for Flask sessions | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DB_PASSWORD` | PostgreSQL password | `a-strong-password` |
| `ADMIN_PASSWORD` | Password for `/admin` | `your-admin-password` |
| `APP_PORT` | Host port to expose (optional) | `5000` (default) |

---

## Manual Docker Compose

```bash
git clone https://github.com/YOURUSERNAME/lacc-film-rcv.git
cd lacc-film-rcv
cp .env.example .env
# Edit .env and fill in SECRET_KEY, DB_PASSWORD, ADMIN_PASSWORD
docker compose up -d
```

The app will be available at `http://localhost:5000`.

---

## Nginx Proxy Manager

Add a proxy host pointing to the Docker host on port `5000` (or whatever `APP_PORT` is set to). NPM passes `X-Forwarded-For` by default — no extra configuration needed.

---

## Admin Workflow

### For a showcase or festival

1. Go to `/admin` and log in
2. Click **Create Poll** — give it a name like `Spring 2026 Film Festival`
3. Download the CSV template and fill in your film list
4. Upload the CSV — films appear instantly with all their metadata
5. Click **Open Poll** and share the URL with students: `/poll/3`
6. When voting closes, click **Close Poll**
7. Results appear immediately on the admin page — round-by-round IRV breakdown

### Multiple events

Each poll is fully independent. You can have a Best of Semester poll and a Film Festival poll running at the same time, or keep old polls closed for historical reference. Students who visit `/` see a list of all currently open polls.

---

## CSV Format

Download the template from the admin panel, or match this structure:

```csv
title,director,class,professor,semester
My Short Film,Jane Smith,Cinema 033,Prof. Garcia,Fall 2025
Another Story,Alex Johnson,Cinema 002,Prof. Kim,Fall 2025
The Final Frame,Sam Lee,Cinema 012,Prof. Patel,Spring 2026
Festival Entry,Casey Brown,Cinema 010,Prof. Nguyen,Spring 2024
```

Only `title` is required. All other columns are optional metadata that appears as pill chips on the ballot.

---

## Updating

GitHub Actions automatically rebuilds the Docker image on every push to `main`. To deploy an update:

1. Push changes to `main`
2. In Dockge, click **Pull & Restart** on the stack

The `pgdata` volume persists across restarts — no data is lost.

---

## Resetting

To wipe all data and start fresh:

```bash
docker compose down -v   # -v removes the pgdata volume
docker compose up -d
```

To clear just the ballots for a specific poll without losing films, use the **Clear All Ballots** button in the admin panel for that poll.

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
