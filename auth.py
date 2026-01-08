import logging
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from db import db_read, db_write

logger = logging.getLogger(__name__)

login_manager = LoginManager()


class User(UserMixin):
    def __init__(self, id, username, password, first_name=None, last_name=None, email=None, license_no=None, club_id=None):
        self.id = id
        self.username = username
        self.password = password
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.license_no = license_no
        self.club_id = club_id

    @staticmethod
    def from_row(row: dict) -> "User":
        return User(
            id=row["id"],
            username=row["username"],
            password=row["password"],
            first_name=row.get("first_name"),
            last_name=row.get("last_name"),
            email=row.get("email"),
            license_no=row.get("license_no"),
            club_id=row.get("club_id"),
        )

    @staticmethod
    def get_by_id(user_id: int):
        row = db_read(
            "SELECT * FROM users WHERE id=%s",
            (user_id,),
            single=True
        )
        if row:
            return User.from_row(row)
        return None

    @staticmethod
    def get_by_username(username: str):
        row = db_read(
            "SELECT * FROM users WHERE username=%s",
            (username,),
            single=True
        )
        if row:
            return User.from_row(row)
        return None


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.get_by_id(int(user_id))
    except Exception:
        logger.exception("load_user failed for user_id=%r", user_id)
        return None


def register_user(first_name: str, last_name: str, email: str, license_no: str, password: str):
    """
    Creates a new user and automatically assigns the club based on license_no.
    Returns: (ok: bool, msg: str)
    """
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    email = (email or "").strip().lower()
    license_no = (license_no or "").strip().upper()

    if not first_name or not last_name or not email or not license_no or not password:
        return False, "Bitte alle Felder ausfüllen."

    # E-Mail bereits registriert?
    if db_read("SELECT id FROM users WHERE email=%s", (email,), single=True):
        return False, "E-Mail ist bereits registriert."

    # Lizenznummer bereits registriert?
    if db_read("SELECT id FROM users WHERE license_no=%s", (license_no,), single=True):
        return False, "Lizenznummer ist bereits registriert."

    # Club anhand Lizenznummer finden
    club_row = db_read("""
        SELECT c.id, c.name
        FROM license_club_map m
        JOIN clubs c ON c.id = m.club_id
        WHERE m.license_no=%s
        LIMIT 1
    """, (license_no,), single=True)

    if not club_row:
        return False, "Lizenznummer unbekannt. Bitte prüfen oder Club kontaktieren."

    club_id = club_row["id"]

    # Wir verwenden E-Mail als username (einfach & robust)
    username = email

    hashed = generate_password_hash(password)

    try:
        db_write("""
            INSERT INTO users (username, password, first_name, last_name, email, license_no, club_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, hashed, first_name, last_name, email, license_no, club_id))
    except Exception:
        logger.exception("DB insert failed in register_user")
        return False, "Fehler beim Registrieren (DB)."

    return True, f"Registrierung erfolgreich. Club erkannt: {club_row['name']}"


def authenticate(username_or_email: str, password: str):
    """
    Authenticates by username (we use email as username).
    Returns User or None
    """
    u = (username_or_email or "").strip().lower()
    if not u or not password:
        return None

    user = User.get_by_username(u)
    if not user:
        return None

    if check_password_hash(user.password, password):
        return user

    return None
