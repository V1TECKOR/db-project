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
    def get_by_id(user_id):
        row = db_read("SELECT * FROM users WHERE id=%s", (user_id,), single=True)
        if row:
            return User(**row)
        return None

    @staticmethod
    def get_by_username(username):
        row = db_read("SELECT * FROM users WHERE username=%s", (username,), single=True)
        if row:
            return User(**row)
        return None


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.get_by_id(int(user_id))
    except Exception:
        return None


def register_user(first_name, last_name, email, license_no, password):
    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip().lower()
    license_no = license_no.strip().upper()

    if not first_name or not last_name or not email or not license_no or not password:
        return False, "Bitte alle Felder ausfüllen."

    if db_read("SELECT id FROM users WHERE email=%s", (email,), single=True):
        return False, "E-Mail ist bereits registriert."

    if db_read("SELECT id FROM users WHERE license_no=%s", (license_no,), single=True):
        return False, "Lizenznummer ist bereits registriert."

    club_row = db_read("""
        SELECT c.id, c.name
        FROM license_club_map m
        JOIN clubs c ON c.id = m.club_id
        WHERE m.license_no=%s
    """, (license_no,), single=True)

    if not club_row:
        return False, "Lizenznummer unbekannt."

    hashed = generate_password_hash(password)

    db_write("""
        INSERT INTO users (username, password, first_name, last_name, email, license_no, club_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (email, hashed, first_name, last_name, email, license_no, club_row["id"]))

    return True, f"Registrierung erfolgreich. Club: {club_row['name']}"


def authenticate(username, password):
    user = User.get_by_username(username.strip().lower())
    if user and check_password_hash(user.password, password):
        return user
    return None
