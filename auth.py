from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from db import db_read, db_write

login_manager = LoginManager()

class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.first_name = row["first_name"]
        self.last_name = row["last_name"]
        self.email = row["email"]
        self.license_number = row["license_number"]
        self.club_id = row["club_id"]
        self.role = row["role"]
        self.password_hash = row["password_hash"]

    @staticmethod
    def by_id(user_id: int):
        row = db_read("SELECT * FROM users WHERE id=%s", (user_id,), single=True)
        return User(row) if row else None

    @staticmethod
    def by_email(email: str):
        row = db_read("SELECT * FROM users WHERE email=%s", (email,), single=True)
        return User(row) if row else None

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.by_id(int(user_id))
    except Exception:
        return None

def _club_from_license(license_number: str):
    # Match by prefix mapping: find the longest prefix that matches start of license number
    mappings = db_read("SELECT license_prefix, club_id FROM license_club_map")
    best = None
    for m in mappings:
        pref = m["license_prefix"]
        if license_number.startswith(pref) and (best is None or len(pref) > len(best["license_prefix"])):
            best = m
    return best["club_id"] if best else None

def register_user(first_name, last_name, email, license_number, password):
    email = email.strip().lower()
    license_number = license_number.strip()

    exists = db_read("SELECT id FROM users WHERE email=%s OR license_number=%s", (email, license_number), single=True)
    if exists:
        return False, "Email oder Lizenznummer existiert bereits."

    club_id = _club_from_license(license_number)
    if not club_id:
        return False, "Lizenznummer nicht bekannt: keine Club-Zuordnung (license_club_map)."

    pw_hash = generate_password_hash(password)

    db_write("""
        INSERT INTO users (first_name,last_name,email,license_number,password_hash,club_id,role)
        VALUES (%s,%s,%s,%s,%s,%s,'player')
    """, (first_name.strip(), last_name.strip(), email, license_number, pw_hash, club_id))

    return True, None

def authenticate(email, password):
    u = User.by_email(email.strip().lower())
    if not u:
        return None
    if check_password_hash(u.password_hash, password):
        return u
    return None
