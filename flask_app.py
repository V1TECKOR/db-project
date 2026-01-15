import os
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message

from db import db_read, db_write
from auth import login_manager, authenticate, register_user

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me")

# Optional email config (works if you set env vars)
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])

mail = Mail(app)

login_manager.init_app(app)
login_manager.login_view = "login"


def send_email(to_email: str, subject: str, body: str) -> None:
    """Send email if SMTP env vars are configured. Otherwise do nothing."""
    if not app.config.get("MAIL_SERVER") or not app.config.get("MAIL_USERNAME"):
        return
    try:
        msg = Message(subject=subject, recipients=[to_email], body=body)
        mail.send(msg)
    except Exception:
        pass


def safe_get_team_id(club_id: int, captain_id: int, name: str) -> int:
    """Fetch latest team id for (club_id, captain_id, name). Safe across connections."""
    row = db_read(
        "SELECT id FROM teams WHERE club_id=%s AND captain_id=%s AND name=%s "
        "ORDER BY id DESC LIMIT 1",
        (club_id, captain_id, name),
        single=True
    )
    if not row:
        raise RuntimeError("Team insert succeeded but could not fetch team id.")
    return int(row["id"])


def safe_get_match_id(team_id: int, opponent: str, location: str) -> int:
    """Fetch latest match id for (team_id, opponent, location). Safe across connections."""
    row = db_read(
        "SELECT id FROM matches WHERE team_id=%s AND opponent=%s AND location=%s "
        "ORDER BY id DESC LIMIT 1",
        (team_id, opponent, location),
        single=True
    )
    if not row:
        raise RuntimeError("Match insert succeeded but could not fetch match id.")
    return int(row["id"])


# ------------------------
# Landing / Auth
# ------------------------

@app.get("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = authenticate(request.form["email"], request.form["password"])
        if user:
            login_user(user)
            flash("Willkommen zurück!", "success")
            return redirect(url_for("dashboard"))
        flash("Login fehlgeschlagen.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        ok, msg = register_user(
            request.form["first_name"],
            request.form["last_name"],
            request.form["email"],
            request.form["license_number"],
            request.form["password"]
        )
        if ok:
            flash("Registrierung erfolgreich. Bitte einloggen.", "success")
            return redirect(url_for("login"))
        flash(msg, "danger")
    return render_template("register.html")


@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("landing"))


# ------------------------
# Dashboard
# ------------------------

@app.get("/dashboard")
@login_required
def dashboard():
    club = db_read("SELECT name FROM clubs WHERE id=%s", (current_user.club_id,), single=True)
    club_name = club["name"] if club else None

    my_teams = db_read("""
        SELECT t.id, t.name, tm.is_approved,
               (t.captain_id=%s) AS is_captain
        FROM team_membership tm
        JOIN teams t ON t.id=tm.team_id
        WHERE tm.user_id=%s
        ORDER BY t.name
    """, (current_user.id, current_user.id))

    upcoming_matches = db_read("""
        SELECT m.id, m.opponent, m.status, m.final_date, t.name AS team_name
        FROM matches m
        JOIN teams t ON t.id=m.team_id
        JOIN team_membership tm ON tm.team_id=t.id
        WHERE tm.user_id=%s AND tm.is_approved=1
        ORDER BY (m.final_date IS NULL), m.final_date, m.created_at DESC
        LIMIT 20
    """, (current_user.id,))

    is_captain_or_admin = current_user.role in ("captain", "club_admin")
    return render_template(
        "dashboard.html",
        club_name=club_name,
        my_teams=my_teams,
        upcoming_matches=upcoming_matches,
        is_captain_or_admin=is_captain_or_admin
    )


# ------------------------
# Teams list
# ------------------------

@app.get("/teams")
@login_required
def teams():
    club = db_read("SELECT name FROM clubs WHERE id=%s", (current_user.club_id,), single=True)
    club_name = club["name"] if club else None

    rows = db_read("""
        SELECT t.id, t.name,
               CONCAT(u.first_name,' ',u.last_name) AS captain_name,
               (t.captain_id=%s) AS is_captain
        FROM teams t
        JOIN users u ON u.id=t.captain_id
        WHERE t.club_id=%s
        ORDER BY t.name
    """, (current_user.id, current_user.club_id))

    mem = db_read("SELECT team_id, is_approved FROM team_membership WHERE user_id=%s", (current_user.id,))
    mem_map = {m["team_id"]: m for m in mem}

    teams_list = []
    for r in rows:
        tid = r["id"]
        teams_list.append({
            "id": tid,
            "name": r["name"],
            "captain_name": r["captain_name"],
            "is_captain": bool(r["is_captain"]),
            "is_my_team": tid in mem_map and mem_map[tid]["is_approved"] == 1,
            "is_pending": tid in mem_map and mem_map[tid]["is_approved"] == 0,
        })

    is_captain_or_admin = current_user.role in ("captain", "club_admin")
    return render_template("teams.html", teams=teams_list, club_name=club_name, is_captain_or_admin=is_captain_or_admin)


# ------------------------
# Team creation (CAPTAIN ONLY)
# ------------------------

@app.get("/team/create")
@login_required
def team_create_route():
    if current_user.role not in ("captain", "club_admin"):
        flash("Nur Captains können Teams erstellen. Bitte wende dich an deinen Club Admin.", "danger")
        return redirect(url_for("teams"))

    return """
    <!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <title>Team erstellen</title>
    </head><body class="p-4">
    <div class="container" style="max-width:720px;">
      <h3 class="mb-3">Team erstellen</h3>
      <div class="text-muted mb-3">
        Nur Benutzer mit Rolle <strong>captain</strong> oder <strong>club_admin</strong> können Teams erstellen.
      </div>
      <form method="post" action="/team/create" class="row g-2">
        <div class="col-md-8">
          <input class="form-control" name="name" placeholder="Teamname" required>
        </div>
        <div class="col-md-4">
          <button class="btn btn-primary w-100">Erstellen</button>
        </div>
      </form>
      <div class="mt-3"><a href="/teams">← zurück</a></div>
    </div></body></html>
    """


@app.post("/team/create")
@login_required
def team_create_route_post():
    if current_user.role not in ("captain", "club_admin"):
        flash("Nur Captains können Teams erstellen.", "danger")
        return redirect(url_for("teams"))

    name = request.form["name"].strip()
    if not name:
        flash("Teamname fehlt.", "danger")
        return redirect(url_for("teams"))

    db_write(
        "INSERT INTO teams (club_id, name, captain_id) VALUES (%s, %s, %s)",
        (current_user.club_id, name, current_user.id)
    )

    team_id = safe_get_team_id(current_user.club_id, current_user.id, name)

    db_write(
        "INSERT INTO team_membership (user_id, team_id, is_approved, approved_at) "
        "VALUES (%s, %s, 1, NOW())",
        (current_user.id, team_id)
    )

    flash("Team erstellt.", "success")
    return redirect(url_for("team_manage", team_id=team_id))


# ------------------------
# Team delete (CAPTAIN / ADMIN)
# ------------------------

def require_captain(team_id: int):
    team = db_read("SELECT * FROM teams WHERE id=%s", (team_id,), single=True)
    if not team:
        return None
    if team["captain_id"] != current_user.id and current_user.role != "club_admin":
        return None
    return team


@app.post("/team/<int:team_id>/delete")
@login_required
def team_delete(team_id):
    team = require_captain(team_id)
    if not team:
        return "Unauthorized", 403

    # Delete everything belonging to this team (manual cascade)
    match_ids = db_read("SELECT id FROM matches WHERE team_id=%s", (team_id,))
    for r in match_ids:
        mid = int(r["id"])
        # messages, tasks, lineup, availability, match_dates, matches
        db_write("DELETE FROM match_messages WHERE match_id=%s", (mid,))
        db_write("DELETE FROM match_tasks WHERE match_id=%s", (mid,))
        db_write("DELETE FROM lineup WHERE match_id=%s", (mid,))
        db_write("""
            DELETE a FROM availability a
            JOIN match_dates md ON md.id=a.match_date_id
            WHERE md.match_id=%s
        """, (mid,))
        db_write("DELETE FROM match_dates WHERE match_id=%s", (mid,))
        db_write("DELETE FROM matches WHERE id=%s", (mid,))

    db_write("DELETE FROM team_membership WHERE team_id=%s", (team_id,))
    db_write("DELETE FROM teams WHERE id=%s", (team_id,))

    flash("Team gelöscht.", "success")
    return redirect(url_for("teams"))


# ------------------------
# Join team (player request)
# ------------------------

@app.post("/team/join")
@login_required
def team_join():
    team_id = int(request.form["team_id"])
    exists = db_read(
        "SELECT * FROM team_membership WHERE user_id=%s AND team_id=%s",
        (current_user.id, team_id),
        single=True
    )
    if exists:
        flash("Du hast bereits eine Anfrage / Mitgliedschaft.", "warning")
        return redirect(url_for("teams"))

    db_write(
        "INSERT INTO team_membership (user_id, team_id, is_approved) VALUES (%s, %s, 0)",
        (current_user.id, team_id)
    )

    captain = db_read("""
        SELECT u.email, u.first_name
        FROM teams t
        JOIN users u ON u.id=t.captain_id
        WHERE t.id=%s
    """, (team_id,), single=True)

    if captain:
        send_email(
            captain["email"],
            "Neue Team-Anfrage",
            f"Hallo {captain['first_name']},\n\nEs gibt eine neue Beitrittsanfrage in deinem Team.\n\n— Interclub Organizer"
        )

    flash("Beitrittsanfrage gesendet.", "success")
    return redirect(url_for("teams"))


# ------------------------
# Team manage
# ------------------------

@app.get("/team/<int:team_id>/manage")
@login_required
def team_manage(team_id):
    team = require_captain(team_id)
    if not team:
        return "Unauthorized", 403

    members = db_read("""
        SELECT u.id,u.first_name,u.last_name,u.email
        FROM team_membership tm
        JOIN users u ON u.id=tm.user_id
        WHERE tm.team_id=%s AND tm.is_approved=1
        ORDER BY u.last_name
    """, (team_id,))

    requests_rows = db_read("""
        SELECT u.id,u.first_name,u.last_name,u.email
        FROM team_membership tm
        JOIN users u ON u.id=tm.user_id
        WHERE tm.team_id=%s AND tm.is_approved=0
        ORDER BY u.last_name
    """, (team_id,))

    matches = db_read("""
        SELECT id, opponent, status, final_date, location
        FROM matches
        WHERE team_id=%s
        ORDER BY created_at DESC
    """, (team_id,))

    return render_template("team_manage.html", team=team, members=members, requests=requests_rows, matches=matches)


@app.post("/team/requests")
@login_required
def team_requests():
    team_id = int(request.form["team_id"])
    user_id = int(request.form["user_id"])
    action = request.form["action"]

    team = require_captain(team_id)
    if not team:
        return "Unauthorized", 403

    if action == "approve":
        db_write(
            "UPDATE team_membership SET is_approved=1, approved_at=NOW() "
            "WHERE user_id=%s AND team_id=%s",
            (user_id, team_id)
        )
        u = db_read("SELECT email, first_name FROM users WHERE id=%s", (user_id,), single=True)
        if u:
            send_email(
                u["email"],
                "Team-Anfrage bestätigt",
                f"Hallo {u['first_name']},\n\nDeine Anfrage wurde akzeptiert.\n\n— Interclub Organizer"
            )
        flash("Anfrage approved.", "success")
    else:
        db_write("DELETE FROM team_membership WHERE user_id=%s AND team_id=%s", (user_id, team_id))
        flash("Anfrage denied.", "warning")

    return redirect(url_for("team_manage", team_id=team_id))


# ------------------------
# Match creation (captain)
# ------------------------

@app.post("/match/create")
@login_required
def match_create():
    team_id = int(request.form["team_id"])
    team = require_captain(team_id)
    if not team:
        return "Unauthorized", 403

    opponent = request.form["opponent"].strip()
    location = request.form["location"].strip()

    db_write(
        "INSERT INTO matches (team_id, opponent, location) VALUES (%s, %s, %s)",
        (team_id, opponent, location)
    )
    match_id = safe_get_match_id(team_id, opponent, location)

    dates = request.form.getlist("proposal_dates")
    for d in dates:
        if d:
            db_write(
                "INSERT INTO match_dates (match_id, proposed_datetime) VALUES (%s, %s)",
                (match_id, d.replace("T", " "))
            )

    members = db_read("""
        SELECT u.email, u.first_name
        FROM team_membership tm JOIN users u ON u.id=tm.user_id
        WHERE tm.team_id=%s AND tm.is_approved=1
    """, (team_id,))
    for m in members:
        send_email(
            m["email"],
            "Neues Match geplant",
            f"Hallo {m['first_name']},\n\nEin neues Match wurde geplant. Bitte trage deine Verfügbarkeit ein.\n\n— Interclub Organizer"
        )

    flash("Match erstellt. Verfügbarkeiten können eingetragen werden.", "success")
    return redirect(url_for("match_detail", match_id=match_id))


# ------------------------
# Match gates
# ------------------------

def require_match_member(match_id: int):
    row = db_read("""
        SELECT m.*, t.name AS team_name, t.captain_id
        FROM matches m JOIN teams t ON t.id=m.team_id
        WHERE m.id=%s
    """, (match_id,), single=True)
    if not row:
        return None, None

    mem = db_read("""
        SELECT * FROM team_membership
        WHERE team_id=%s AND user_id=%s AND is_approved=1
    """, (row["team_id"], current_user.id), single=True)

    if not mem and current_user.role != "club_admin":
        return None, None

    return row, row["team_name"]


def require_match_captain(match_id: int):
    row = db_read("""
        SELECT m.*, t.captain_id
        FROM matches m JOIN teams t ON t.id=m.team_id
        WHERE m.id=%s
    """, (match_id,), single=True)
    if not row:
        return None
    if row["captain_id"] != current_user.id and current_user.role != "club_admin":
        return None
    return row


# ------------------------
# Match detail (players can volunteer + message)
# ------------------------

@app.get("/match/<int:match_id>")
@login_required
def match_detail(match_id):
    match, team_name = require_match_member(match_id)
    if not match:
        return "Unauthorized", 403

    is_captain = (match["captain_id"] == current_user.id) or (current_user.role == "club_admin")

    date_options = db_read("SELECT * FROM match_dates WHERE match_id=%s ORDER BY proposed_datetime", (match_id,))
    my_av = db_read("""
        SELECT md.id
        FROM availability a
        JOIN match_dates md ON md.id=a.match_date_id
        WHERE md.match_id=%s AND a.user_id=%s AND a.available=1
    """, (match_id, current_user.id))
    my_date_ids = {r["id"] for r in my_av}

    date_summaries = []
    if is_captain and match["status"] == "planned":
        for d in date_options:
            rows = db_read("""
                SELECT u.first_name,u.last_name
                FROM availability a JOIN users u ON u.id=a.user_id
                WHERE a.match_date_id=%s AND a.available=1
                ORDER BY u.last_name
            """, (d["id"],))
            names = ", ".join([f"{r['first_name']} {r['last_name']}" for r in rows]) if rows else "—"
            date_summaries.append({
                "id": d["id"],
                "proposed_datetime": d["proposed_datetime"],
                "count": len(rows),
                "names": names
            })

    members = db_read("""
        SELECT u.id,u.first_name,u.last_name
        FROM team_membership tm JOIN users u ON u.id=tm.user_id
        WHERE tm.team_id=%s AND tm.is_approved=1
        ORDER BY u.last_name
    """, (match["team_id"],))

    lineup_rows = db_read("SELECT user_id, confirmed FROM lineup WHERE match_id=%s", (match_id,))
    lineup_ids = {r["user_id"] for r in lineup_rows}
    in_lineup = current_user.id in lineup_ids
    confirmed = any(r["user_id"] == current_user.id and r["confirmed"] == 1 for r in lineup_rows)

    lineup_status = []
    if is_captain and lineup_rows:
        for r in lineup_rows:
            u = db_read("SELECT first_name,last_name FROM users WHERE id=%s", (r["user_id"],), single=True)
            if u:
                lineup_status.append({"name": f"{u['first_name']} {u['last_name']}", "confirmed": bool(r["confirmed"])})

    tasks = ["Balls", "Drinks", "Transport"]
    task_rows = db_read("""
        SELECT task, CONCAT(u.first_name,' ',u.last_name) AS name
        FROM match_tasks mt JOIN users u ON u.id=mt.user_id
        WHERE mt.match_id=%s
    """, (match_id,))
    task_assignments = {r["task"]: r["name"] for r in task_rows}

    messages = db_read("""
        SELECT mm.content, mm.created_at, CONCAT(u.first_name,' ',u.last_name) AS author
        FROM match_messages mm JOIN users u ON u.id=mm.user_id
        WHERE mm.match_id=%s
        ORDER BY mm.created_at DESC
        LIMIT 50
    """, (match_id,))
    messages = list(reversed(messages))

    back_url = url_for("team_manage", team_id=match["team_id"]) if is_captain else url_for("dashboard")

    return render_template(
        "match_detail.html",
        match=match,
        team_name=team_name,
        back_url=back_url,
        is_captain=is_captain,
        date_options=date_options,
        my_date_ids=my_date_ids,
        date_summaries=date_summaries,
        members=members,
        lineup_ids=lineup_ids,
        in_lineup=in_lineup,
        confirmed=confirmed,
        lineup_status=lineup_status,
        tasks=tasks,
        task_assignments=task_assignments,
        messages=messages
    )


# ------------------------
# Captain edits match (opponent/location + reset proposed dates)
# ------------------------

@app.get("/match/<int:match_id>/edit")
@login_required
def match_edit(match_id):
    row = require_match_captain(match_id)
    if not row:
        return "Unauthorized", 403

    # inline editor page (no template needed)
    return f"""
    <!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <title>Match bearbeiten</title>
    </head><body class="p-4">
    <div class="container" style="max-width:860px;">
      <h3 class="mb-3">Match bearbeiten</h3>
      <form method="post" action="/match/{match_id}/edit" class="card p-3">
        <div class="mb-3">
          <label class="form-label">Opponent</label>
          <input class="form-control" name="opponent" value="{row.get('opponent','')}" required>
        </div>
        <div class="mb-3">
          <label class="form-label">Location</label>
          <input class="form-control" name="location" value="{row.get('location','')}" required>
        </div>
        <div class="mb-3">
          <label class="form-label">Neue Vorschlagsdaten (optional, überschreibt alles)</label>
          <div class="text-muted mb-2">Format: HTML datetime-local. Lass leer, wenn du nur Opponent/Location ändern willst.</div>
          <input class="form-control mb-2" type="datetime-local" name="proposal_dates">
          <input class="form-control mb-2" type="datetime-local" name="proposal_dates">
          <input class="form-control mb-2" type="datetime-local" name="proposal_dates">
        </div>
        <button class="btn btn-primary">Speichern</button>
        <a class="btn btn-link" href="/match/{match_id}">Abbrechen</a>
      </form>

      <form method="post" action="/match/{match_id}/delete" class="mt-3"
            onsubmit="return confirm('Match wirklich löschen?');">
        <button class="btn btn-danger">Match löschen</button>
      </form>
    </div></body></html>
    """


@app.post("/match/<int:match_id>/edit")
@login_required
def match_edit_post(match_id):
    row = require_match_captain(match_id)
    if not row:
        return "Unauthorized", 403

    opponent = request.form["opponent"].strip()
    location = request.form["location"].strip()

    db_write(
        "UPDATE matches SET opponent=%s, location=%s WHERE id=%s",
        (opponent, location, match_id)
    )

    # If proposal_dates provided, reset schedule (and availability based on old dates)
    proposed = [d for d in request.form.getlist("proposal_dates") if d]
    if proposed:
        # delete availability for this match
        db_write("""
            DELETE a FROM availability a
            JOIN match_dates md ON md.id=a.match_date_id
            WHERE md.match_id=%s
        """, (match_id,))
        db_write("DELETE FROM match_dates WHERE match_id=%s", (match_id,))

        for d in proposed:
            db_write(
                "INSERT INTO match_dates (match_id, proposed_datetime) VALUES (%s, %s)",
                (match_id, d.replace("T", " "))
            )

        # revert to planned if dates changed
        db_write(
            "UPDATE matches SET status='planned', final_date=NULL WHERE id=%s",
            (match_id,)
        )

    flash("Match gespeichert.", "success")
    return redirect(url_for("match_detail", match_id=match_id))


@app.post("/match/<int:match_id>/delete")
@login_required
def match_delete(match_id):
    row = require_match_captain(match_id)
    if not row:
        return "Unauthorized", 403

    # Delete match-related
    db_write("DELETE FROM match_messages WHERE match_id=%s", (match_id,))
    db_write("DELETE FROM match_tasks WHERE match_id=%s", (match_id,))
    db_write("DELETE FROM lineup WHERE match_id=%s", (match_id,))
    db_write("""
        DELETE a FROM availability a
        JOIN match_dates md ON md.id=a.match_date_id
        WHERE md.match_id=%s
    """, (match_id,))
    db_write("DELETE FROM match_dates WHERE match_id=%s", (match_id,))
    db_write("DELETE FROM matches WHERE id=%s", (match_id,))

    flash("Match gelöscht.", "success")
    return redirect(url_for("team_manage", team_id=row["team_id"]))


# ------------------------
# Availability submit (players)
# ------------------------

@app.post("/match/availability")
@login_required
def match_availability():
    match_id = int(request.form["match_id"])
    match, _ = require_match_member(match_id)
    if not match:
        return "Unauthorized", 403

    selected = {int(x) for x in request.form.getlist("date_ids")}

    db_write("""
        DELETE a FROM availability a
        JOIN match_dates md ON md.id=a.match_date_id
        WHERE md.match_id=%s AND a.user_id=%s
    """, (match_id, current_user.id))

    for date_id in selected:
        db_write(
            "INSERT INTO availability (match_date_id, user_id, available) VALUES (%s, %s, 1)",
            (date_id, current_user.id)
        )

    flash("Verfügbarkeit gespeichert.", "success")
    return redirect(url_for("match_detail", match_id=match_id))


# ------------------------
# Captain confirms date
# ------------------------

@app.post("/match/confirm_date")
@login_required
def match_confirm_date():
    match_id = int(request.form["match_id"])
    date_id = int(request.form["date_id"])

    match = db_read("""
        SELECT m.id, m.team_id, t.captain_id
        FROM matches m JOIN teams t ON t.id=m.team_id
        WHERE m.id=%s
    """, (match_id,), single=True)
    if not match:
        return "Not found", 404
    if match["captain_id"] != current_user.id and current_user.role != "club_admin":
        return "Unauthorized", 403

    d = db_read(
        "SELECT proposed_datetime FROM match_dates WHERE id=%s AND match_id=%s",
        (date_id, match_id),
        single=True
    )
    if not d:
        return "Invalid date", 400

    db_write(
        "UPDATE matches SET status='confirmed', final_date=%s WHERE id=%s",
        (d["proposed_datetime"], match_id)
    )

    flash("Datum bestätigt. Jetzt Lineup & Logistik.", "success")
    return redirect(url_for("match_detail", match_id=match_id))


# ------------------------
# Captain sets lineup
# ------------------------

@app.post("/match/set_lineup")
@login_required
def match_set_lineup():
    match_id = int(request.form["match_id"])

    match = db_read("""
        SELECT m.team_id, t.captain_id
        FROM matches m JOIN teams t ON t.id=m.team_id
        WHERE m.id=%s
    """, (match_id,), single=True)
    if not match:
        return "Not found", 404
    if match["captain_id"] != current_user.id and current_user.role != "club_admin":
        return "Unauthorized", 403

    selected = {int(x) for x in request.form.getlist("player_ids")}

    db_write("DELETE FROM lineup WHERE match_id=%s", (match_id,))
    for uid in selected:
        db_write(
            "INSERT INTO lineup (match_id, user_id, confirmed) VALUES (%s, %s, 0)",
            (match_id, uid)
        )

    flash("Lineup gespeichert. Spieler bestätigen selbst.", "success")
    return redirect(url_for("match_detail", match_id=match_id))


# ------------------------
# Player confirms lineup
# ------------------------

@app.post("/match/confirm_lineup")
@login_required
def match_confirm_lineup():
    match_id = int(request.form["match_id"])
    response = request.form["response"]

    row = db_read(
        "SELECT * FROM lineup WHERE match_id=%s AND user_id=%s",
        (match_id, current_user.id),
        single=True
    )
    if not row:
        return "Unauthorized", 403

    if response == "yes":
        db_write(
            "UPDATE lineup SET confirmed=1 WHERE match_id=%s AND user_id=%s",
            (match_id, current_user.id)
        )
        flash("Teilnahme bestätigt.", "success")
    else:
        db_write(
            "DELETE FROM lineup WHERE match_id=%s AND user_id=%s",
            (match_id, current_user.id)
        )
        flash("Du kannst nicht spielen (Captain sieht es).", "warning")

    return redirect(url_for("match_detail", match_id=match_id))


# ------------------------
# Volunteer a logistics task (players too; first gets it)
# ------------------------

@app.post("/match/task")
@login_required
def match_task():
    match_id = int(request.form["match_id"])
    task = request.form["task"]

    match, _ = require_match_member(match_id)
    if not match:
        return "Unauthorized", 403

    exists = db_read(
        "SELECT * FROM match_tasks WHERE match_id=%s AND task=%s",
        (match_id, task),
        single=True
    )
    if exists:
        flash("Task ist bereits vergeben.", "warning")
        return redirect(url_for("match_detail", match_id=match_id))

    db_write(
        "INSERT INTO match_tasks (match_id, task, user_id) VALUES (%s, %s, %s)",
        (match_id, task, current_user.id)
    )

    flash(f"Du übernimmst: {task}", "success")
    return redirect(url_for("match_detail", match_id=match_id))


# ------------------------
# Post a message (players too)
# ------------------------

@app.post("/match/message")
@login_required
def match_message():
    match_id = int(request.form["match_id"])
    content = request.form["content"].strip()

    match, _ = require_match_member(match_id)
    if not match:
        return "Unauthorized", 403

    if not content:
        flash("Nachricht leer.", "warning")
        return redirect(url_for("match_detail", match_id=match_id))

    db_write(
        "INSERT INTO match_messages (match_id, user_id, content) VALUES (%s, %s, %s)",
        (match_id, current_user.id, content)
    )
    return redirect(url_for("match_detail", match_id=match_id))


if __name__ == "__main__":
    app.run(debug=True)
