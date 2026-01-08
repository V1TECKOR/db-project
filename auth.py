import logging
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from db import db_read, db_write

# Logger für dieses Modul
logger = logging.getLogger(__name__)

login_manager = LoginManager()


class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

    @staticmethod
    def register_user(first_name, last_name, email, license_no, password):
    logger.info("register_user(): neuer User %s %s (%s) lic=%s", first_name, last_name, email, license_no)

    # 1) E-Mail schon vorhanden?
    existing_email = db_read("SELECT id FROM users WHERE email=%s", (email,), single=True)
    if existing_email:
        return False, "E-Mail ist bereits registriert."

    # 2) Lizenznummer schon vorhanden?
    existing_lic = db_read("SELECT id FROM users WHERE license_no=%s", (license_no,), single=True)
    if existing_lic:
        return False, "Lizenznummer ist bereits registriert."

    # 3) Club anhand Lizenznummer finden
    club_row = db_read("""
        SELECT c.id, c.name
        FROM license_club_map m
        JOIN clubs c ON c.id = m.club_id
        WHERE m.license_no=%s
        LIMIT 1
    """, (license_no,), single=True)

    if not club_row:
        return False, "Lizenznummer unbekannt. Bitte prüfe die Eingabe oder kontaktiere den Club."

    club_id = club_row["id"]

    # 4) Username automatisch aus Email machen (oder du definierst eigene Regel)
    username = email  # simplest: username = email

    # 5) Passwort hashen + speichern
    hashed = generate_password_hash(password)
    try:
        db_write("""
            INSERT INTO users (username, password, first_name, last_name, email, license_no, club_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, hashed, first_name, last_name, email, license_no, club_id))
    except Exception:
        logger.exception("Fehler beim Anlegen des Users")
        return False, "Fehler beim Registrieren (DB)."

    return True, f"Registrierung erfolgreich. Club erkannt: {club_row['name']}"

    @staticmethod
    def get_by_username(username):
        logger.debug("User.get_by_username() aufgerufen mit username=%s", username)
        try:
            row = db_read(
                "SELECT * FROM users WHERE username = %s",
                (username,),
                single=True
            )
            logger.debug("User.get_by_username() DB-Ergebnis: %r", row)
        except Exception:
            logger.exception("Fehler bei User.get_by_username(%s)", username)
            return None

        if row:
            return User(row["id"], row["username"], row["password"])
        else:
            logger.info("User.get_by_username(): kein User mit username=%s", username)
            return None


# Flask-Login
@login_manager.user_loader
def load_user(user_id):
    logger.debug("load_user() aufgerufen mit user_id=%s", user_id)
    try:
        user = User.get_by_id(int(user_id))
    except ValueError:
        logger.error("load_user(): user_id=%r ist keine int", user_id)
        return None

    if user:
        logger.debug("load_user(): User gefunden: %s (id=%s)", user.username, user.id)
    else:
        logger.warning("load_user(): kein User für id=%s gefunden", user_id)

    return user


# Helpers
def register_user(first_name, last_name, email, license_no, password):
    # NOTE: 4 spaces indentation in this function is REQUIRED
    logger.info(
        "register_user(): neuer User %s %s (%s) lic=%s",
        first_name, last_name, email, license_no
    )

    existing_email = db_read(
        "SELECT id FROM users WHERE email=%s",
        (email,),
        single=True
    )
    if existing_email:
        return False, "E-Mail ist bereits registriert."

    existing_lic = db_read(
        "SELECT id FROM users WHERE license_no=%s",
        (license_no,),
        single=True
    )
    if existing_lic:
        return False, "Lizenznummer ist bereits registriert."

    club_row = db_read("""
        SELECT c.id, c.name
        FROM license_club_map m
        JOIN clubs c ON c.id = m.club_id
        WHERE m.license_no=%s
        LIMIT 1
    """, (license_no,), single=True)

    if not club_row:
        return False, "Lizenznummer unbekannt. Bitte prüfe die Eingabe."

    club_id = club_row["id"]
    username = email
    hashed = generate_password_hash(password)

    try:
        db_write("""
            INSERT INTO users (username, password, first_name, last_name, email, license_no, club_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, hashed, first_name, last_name, email, license_no, club_id))
    except Exception:
        logger.exception("Fehler beim Anlegen des Users")
        return False, "Fehler beim Registrieren (DB)."

    return True, f"Registrierung erfolgreich. Club erkannt: {club_row['name']}"


def authenticate(username, password):
    logger.info("authenticate(): Login-Versuch für '%s'", username)
    user = User.get_by_username(username)

    if not user:
        logger.warning("authenticate(): kein User mit username='%s' gefunden", username)
        return None

    if check_password_hash(user.password, password):
        logger.info("authenticate(): Passwort korrekt für '%s'", username)
        return user

    logger.warning("authenticate(): falsches Passwort für '%s'", username)
    return None
