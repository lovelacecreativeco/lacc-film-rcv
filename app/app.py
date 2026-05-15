import os
import csv
import json
import uuid
import io
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, make_response
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key   = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "postgresql://rcv:rcvpass@db:5432/rcvdb"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

COOKIE_PREFIX  = "rcv_voter_"          # + poll_id  =>  rcv_voter_3
COOKIE_MAX_AGE = int(os.environ.get("COOKIE_MAX_AGE_DAYS", 365)) * 86400
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

db = SQLAlchemy(app)


# ── Class color map ───────────────────────────────────────────────────────────
# Keyed by the normalized class number (upper, no spaces).
CLASS_COLORS = {
    "CINEMA002": {"bg": "#1a3a1a", "text": "#6fcf6f", "border": "#4caf50"},
    "CINEMA010": {"bg": "#1a2a3a", "text": "#6fb3cf", "border": "#4090c0"},
    "CINEMA012": {"bg": "#2a1a3a", "text": "#b36fcf", "border": "#9040c0"},
    "CINEMA033": {"bg": "#3a2a1a", "text": "#cfac6f", "border": "#c09040"},
}
CLASS_LABELS = {
    "CINEMA002": "Cinema 002",
    "CINEMA010": "Cinema 010",
    "CINEMA012": "Cinema 012",
    "CINEMA033": "Cinema 033",
}
# Any other class number gets this fallback
CLASS_FALLBACK = {"bg": "#1a1a2e", "text": "#8888cc", "border": "#5555aa"}


def class_style(raw_class: str):
    """Return (label, color_dict) for a raw class string."""
    if not raw_class:
        return None, None
    key = raw_class.upper().replace(" ", "").replace("-", "")
    label  = CLASS_LABELS.get(key, raw_class)
    colors = CLASS_COLORS.get(key, CLASS_FALLBACK)
    return label, colors


# ── Models ────────────────────────────────────────────────────────────────────

class Poll(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    is_open     = db.Column(db.Boolean, default=False)
    top_n       = db.Column(db.Integer, default=5)   # how many picks voters make
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    films       = db.relationship("Film",   backref="poll", lazy=True, cascade="all, delete-orphan")
    ballots     = db.relationship("Ballot", backref="poll", lazy=True, cascade="all, delete-orphan")


class Film(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    poll_id    = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    title      = db.Column(db.String(200), nullable=False)
    student    = db.Column(db.String(200), default="")
    genre      = db.Column(db.String(100), default="")
    semester   = db.Column(db.String(50),  default="")
    class_num  = db.Column(db.String(50),  default="")
    professor  = db.Column(db.String(100), default="")
    sort_order = db.Column(db.Integer,     default=0)   # preserves CSV upload order
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Ballot(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    poll_id      = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    voter_token  = db.Column(db.String(64), nullable=False)
    ranking      = db.Column(db.Text, nullable=False)   # JSON list of film IDs
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("poll_id", "voter_token"),)


# ── IRV ───────────────────────────────────────────────────────────────────────

def run_irv(ballots, film_map):
    if not ballots or not film_map:
        return [], None

    candidates = set(film_map.keys())
    eliminated = set()
    rounds     = []
    winner     = None

    while True:
        counts    = {c: 0 for c in candidates - eliminated}
        exhausted = 0

        for ballot in ballots:
            top = next(
                (fid for fid in ballot if fid in candidates and fid not in eliminated),
                None,
            )
            if top is not None:
                counts[top] += 1
            else:
                exhausted += 1

        total = sum(counts.values())
        rd = {
            "counts":     {film_map[fid]: cnt for fid, cnt in counts.items()},
            "exhausted":  exhausted,
            "total":      total,
            "eliminated": None,
            "winner":     None,
        }

        if total == 0:
            rounds.append(rd)
            break

        for fid, cnt in counts.items():
            if cnt > total / 2:
                winner = film_map[fid]
                rd["winner"] = winner
                rounds.append(rd)
                return rounds, winner

        min_v    = min(counts.values())
        to_elim  = [fid for fid, cnt in counts.items() if cnt == min_v]

        if len(to_elim) == len(counts):          # full tie
            best   = max(counts, key=lambda x: counts[x])
            winner = film_map[best]
            rd["winner"] = winner
            rounds.append(rd)
            return rounds, winner

        eliminated.update(to_elim)
        rd["eliminated"] = [film_map[fid] for fid in to_elim]
        rounds.append(rd)
        candidates -= eliminated

        if len(candidates) == 1:
            last = next(iter(candidates))
            winner = film_map[last]
            rounds[-1]["winner"] = winner
            return rounds, winner

        if not candidates:
            break

    return rounds, winner


# ── Helpers ───────────────────────────────────────────────────────────────────

def cookie_name(poll_id):
    return f"{COOKIE_PREFIX}{poll_id}"


def enrich_films(films):
    """Add .class_label, .class_colors, and .genre_list to each film object in-place."""
    for f in films:
        f.class_label, f.class_colors = class_style(f.class_num)
        # Parse comma-separated genres into a cleaned list, drop empties
        f.genre_list = [g.strip() for g in (f.genre or "").split(",") if g.strip()]
    return films


# ── Public: poll listing ──────────────────────────────────────────────────────

@app.route("/")
def index():
    open_polls = Poll.query.filter_by(is_open=True).order_by(Poll.created_at.desc()).all()
    if len(open_polls) == 1:
        return redirect(url_for("ballot", poll_id=open_polls[0].id))
    return render_template("index.html", polls=open_polls)


# ── Public: ballot ────────────────────────────────────────────────────────────

@app.route("/poll/<int:poll_id>")
def ballot(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if not poll.is_open:
        return render_template("closed.html", poll=poll)

    voter_token   = request.cookies.get(cookie_name(poll_id))
    already_voted = bool(
        voter_token and
        Ballot.query.filter_by(poll_id=poll_id, voter_token=voter_token).first()
    )

    films = enrich_films(Film.query.filter_by(poll_id=poll_id).order_by(Film.sort_order, Film.id).all())
    return render_template("ballot.html", poll=poll, films=films, already_voted=already_voted, top_n=poll.top_n)


@app.route("/poll/<int:poll_id>/vote", methods=["POST"])
def vote(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if not poll.is_open:
        flash("This poll is not open.", "error")
        return redirect(url_for("ballot", poll_id=poll_id))

    voter_token = request.cookies.get(cookie_name(poll_id)) or str(uuid.uuid4())

    if Ballot.query.filter_by(poll_id=poll_id, voter_token=voter_token).first():
        flash("A ballot has already been submitted from this browser.", "error")
        return redirect(url_for("ballot", poll_id=poll_id))

    try:
        ranking = [int(x) for x in json.loads(request.form.get("ranking", "[]"))]
    except (ValueError, TypeError):
        flash("Invalid ballot.", "error")
        return redirect(url_for("ballot", poll_id=poll_id))

    valid_ids = {f.id for f in Film.query.filter_by(poll_id=poll_id).all()}
    if not ranking or not all(fid in valid_ids for fid in ranking):
        flash("Invalid ballot: unknown films.", "error")
        return redirect(url_for("ballot", poll_id=poll_id))

    db.session.add(Ballot(poll_id=poll_id, voter_token=voter_token, ranking=json.dumps(ranking)))
    db.session.commit()

    resp = make_response(redirect(url_for("thank_you", poll_id=poll_id)))
    resp.set_cookie(cookie_name(poll_id), voter_token,
                    max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax")
    return resp


@app.route("/poll/<int:poll_id>/thanks")
def thank_you(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    return render_template("thank_you.html", poll=poll)


# ── Admin auth ────────────────────────────────────────────────────────────────

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_home"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


# ── Admin: poll list ──────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_home():
    polls = Poll.query.order_by(Poll.created_at.desc()).all()
    for p in polls:
        p.ballot_count = Ballot.query.filter_by(poll_id=p.id).count()
        p.film_count   = Film.query.filter_by(poll_id=p.id).count()
    return render_template("admin_home.html", polls=polls)


@app.route("/admin/polls/create", methods=["POST"])
@admin_required
def admin_create_poll():
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    try:
        top_n = max(1, int(request.form.get("top_n", 5)))
    except (ValueError, TypeError):
        top_n = 5
    if not name:
        flash("Poll name is required.", "error")
        return redirect(url_for("admin_home"))
    poll = Poll(name=name, description=desc, top_n=top_n)
    db.session.add(poll)
    db.session.commit()
    flash(f'Poll "{name}" created.', "success")
    return redirect(url_for("admin_poll", poll_id=poll.id))


@app.route("/admin/polls/<int:poll_id>/delete", methods=["POST"])
@admin_required
def admin_delete_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    name = poll.name
    db.session.delete(poll)
    db.session.commit()
    flash(f'Poll "{name}" deleted.', "success")
    return redirect(url_for("admin_home"))


# ── Admin: poll detail ────────────────────────────────────────────────────────

@app.route("/admin/polls/<int:poll_id>")
@admin_required
def admin_poll(poll_id):
    poll         = Poll.query.get_or_404(poll_id)
    films        = enrich_films(Film.query.filter_by(poll_id=poll_id).order_by(Film.sort_order, Film.id).all())
    ballot_count = Ballot.query.filter_by(poll_id=poll_id).count()

    rounds, winner = None, None
    if not poll.is_open and ballot_count > 0:
        film_map       = {f.id: f.title for f in films}
        ballots        = [json.loads(b.ranking) for b in Ballot.query.filter_by(poll_id=poll_id).all()]
        rounds, winner = run_irv(ballots, film_map)

    return render_template(
        "admin_poll.html",
        poll=poll,
        films=films,
        ballot_count=ballot_count,
        rounds=rounds,
        winner=winner,
    )


@app.route("/admin/polls/<int:poll_id>/open", methods=["POST"])
@admin_required
def admin_open_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    if Film.query.filter_by(poll_id=poll_id).count() == 0:
        flash("Add at least one film before opening the poll.", "error")
        return redirect(url_for("admin_poll", poll_id=poll_id))
    poll.is_open = True
    db.session.commit()
    flash("Poll is now open.", "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/polls/<int:poll_id>/close", methods=["POST"])
@admin_required
def admin_close_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    poll.is_open = False
    db.session.commit()
    flash("Poll closed. IRV results shown below.", "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/polls/<int:poll_id>/rename", methods=["POST"])
@admin_required
def admin_rename_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    try:
        top_n = max(1, int(request.form.get("top_n", 5)))
    except (ValueError, TypeError):
        top_n = 5
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("admin_poll", poll_id=poll_id))
    poll.name        = name
    poll.description = desc
    poll.top_n       = top_n
    db.session.commit()
    flash("Poll updated.", "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


# ── Admin: films ──────────────────────────────────────────────────────────────

@app.route("/admin/polls/<int:poll_id>/films/add", methods=["POST"])
@admin_required
def admin_add_film(poll_id):
    Poll.query.get_or_404(poll_id)
    title     = request.form.get("title",     "").strip()
    student   = request.form.get("student",   "").strip()
    genre     = request.form.get("genre",     "").strip()
    semester  = request.form.get("semester",  "").strip()
    class_num = request.form.get("class_num", "").strip()
    professor = request.form.get("professor", "").strip()
    if not title:
        flash("Film title is required.", "error")
        return redirect(url_for("admin_poll", poll_id=poll_id))
    # Place manually added films after all existing ones
    max_order = db.session.query(db.func.max(Film.sort_order)).filter_by(poll_id=poll_id).scalar() or 0
    db.session.add(Film(
        poll_id=poll_id, title=title, student=student, genre=genre,
        semester=semester, class_num=class_num, professor=professor,
        sort_order=max_order + 1,
    ))
    db.session.commit()
    flash(f'"{title}" added.', "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/polls/<int:poll_id>/films/<int:film_id>/delete", methods=["POST"])
@admin_required
def admin_delete_film(poll_id, film_id):
    film = Film.query.filter_by(id=film_id, poll_id=poll_id).first_or_404()
    db.session.delete(film)
    db.session.commit()
    flash(f'"{film.title}" removed.', "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/polls/<int:poll_id>/films/upload", methods=["POST"])
@admin_required
def admin_upload_csv(poll_id):
    Poll.query.get_or_404(poll_id)
    f = request.files.get("csv_file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Please upload a .csv file.", "error")
        return redirect(url_for("admin_poll", poll_id=poll_id))

    stream  = io.StringIO(f.stream.read().decode("utf-8-sig"))
    reader  = csv.DictReader(stream)
    headers = {c.strip().lower() for c in (reader.fieldnames or [])}

    if "title" not in headers:
        flash("CSV must include a 'title' column.", "error")
        return redirect(url_for("admin_poll", poll_id=poll_id))

    added, skipped = 0, 0
    # Start sort_order after any existing films in this poll
    max_order = db.session.query(db.func.max(Film.sort_order)).filter_by(poll_id=poll_id).scalar() or 0
    next_order = max_order + 1

    for row in reader:
        row       = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
        title     = row.get("title", "")
        if not title:
            skipped += 1
            continue
        db.session.add(Film(
            poll_id    = poll_id,
            title      = title,
            student    = row.get("student",   ""),
            genre      = row.get("genre",     ""),
            semester   = row.get("semester",  ""),
            class_num  = row.get("class",     ""),
            professor  = row.get("professor", ""),
            sort_order = next_order,
        ))
        next_order += 1
        added += 1

    db.session.commit()
    flash(f"{added} film(s) imported, {skipped} row(s) skipped.", "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/films/template")
@admin_required
def admin_csv_template():
    out    = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["title", "student", "genre", "class", "professor", "semester"])
    writer.writerow(["My Short Film",      "Jane Smith",   "Drama, Thriller",    "Cinema 033", "Prof. Garcia",  "Fall 2025"])
    writer.writerow(["Another Story",      "Alex Johnson", "Documentary",        "Cinema 002", "Prof. Kim",     "Fall 2025"])
    writer.writerow(["The Final Frame",    "Sam Lee",      "Horror, Sci-Fi",     "Cinema 012", "Prof. Patel",   "Spring 2026"])
    writer.writerow(["Festival Entry One", "Casey Brown",  "Comedy",             "Cinema 010", "Prof. Nguyen",  "Spring 2024"])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"]        = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=films_template.csv"
    return resp


@app.route("/admin/polls/<int:poll_id>/ballots/clear", methods=["POST"])
@admin_required
def admin_clear_ballots(poll_id):
    Poll.query.get_or_404(poll_id)
    Ballot.query.filter_by(poll_id=poll_id).delete()
    db.session.commit()
    flash("All ballots cleared.", "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/polls/<int:poll_id>/films/clear", methods=["POST"])
@admin_required
def admin_clear_films(poll_id):
    Poll.query.get_or_404(poll_id)
    Film.query.filter_by(poll_id=poll_id).delete()
    db.session.commit()
    flash("All films cleared.", "success")
    return redirect(url_for("admin_poll", poll_id=poll_id))


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
