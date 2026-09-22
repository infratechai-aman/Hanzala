"""Admin user model.

Password helpers only — no login system in this milestone.
Passwords are never stored as plaintext (Werkzeug hashing).
"""

from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db


class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        """Hash and store a plaintext password (never stored as-is)."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Return True if the plaintext password matches the stored hash."""
        return check_password_hash(self.password_hash, password)
