"""Application configuration.

Configuration lives here, separate from application initialization
in app/__init__.py, so environment-specific settings can be selected
without importing the Flask app (avoids circular imports).

Secrets are read from environment variables (see .env). Nothing
secret is hard-coded here; fallbacks are dev-only conveniences.
"""

import os
from datetime import timedelta

from dotenv import load_dotenv
from sqlalchemy.pool import StaticPool

# Load .env before reading os.getenv below, so both `run.py`
# and direct `create_app()` imports (e.g. tests) see the same values.
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    # Default to a local SQLite file inside instance/ (Flask's
    # convention for deployment-specific data that stays out of git).
    _raw_db_url = os.getenv("DATABASE_URL")
    if _raw_db_url and _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    if not _raw_db_url:
        is_serverless = bool(
            os.getenv("VERCEL")
            or os.getenv("VERCEL_ENV")
            or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
            or os.getenv("LAMBDA_TASK_ROOT")
        )
        if is_serverless:
            # On Vercel / Lambda (Linux), /tmp is the only writable directory.
            _raw_db_url = "sqlite:////tmp/app.db"
        else:
            try:
                _default_db_dir = os.path.join(BASE_DIR, "instance")
                os.makedirs(_default_db_dir, exist_ok=True)
                _raw_db_url = "sqlite:///" + os.path.join(_default_db_dir, "app.db")
            except OSError:
                _raw_db_url = "sqlite:////tmp/app.db"

    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Persistent media storage root. Uploaded files live here and are
    # served to browsers through the static route, so the default stays
    # inside app/static. Override with the MEDIA_ROOT env var to point at
    # a persistent disk (e.g. a mounted volume in production).
    #
    # Deployment reality: most PaaS app filesystems are ephemeral — local
    # uploads are wiped on redeploy/restart there. This setting is the
    # single seam for moving storage later (persistent disk, then object
    # storage) without rewriting the portfolio. For permanent public
    # assets on ephemeral hosting, prefer remote (http) media instead.
    MEDIA_ROOT = os.getenv(
        "MEDIA_ROOT",
        "/tmp/media"
        if (
            os.getenv("VERCEL")
            or os.getenv("VERCEL_ENV")
            or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
            or os.getenv("LAMBDA_TASK_ROOT")
        )
        else os.path.join(BASE_DIR, "app", "static", "uploads", "media"),
    )

    # Session cookie hardening. Cookie is never sent over plain HTTP
    # unless explicitly allowed for local development via env.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.getenv("SESSION_LIFETIME_HOURS", "8"))
    )


class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration: no debug, always secure cookies."""

    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Configuration used by the test suite (in-memory DB)."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Single shared connection so the in-memory database survives
    # across pooled checkouts within a test.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
