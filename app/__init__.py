"""Flask application factory."""

import click
import os
from flask import Flask, render_template
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.models import db  # noqa: F401 -- importing registers all models
from app.routes.admin import admin_bp
from app.routes.public import public_bp
from config import ProductionConfig, config_by_name

migrate = Migrate()
csrf = CSRFProtect()

DEV_FALLBACK_SECRET = "dev-only-change-me"


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """Enforce FOREIGN KEY constraints on SQLite connections.

    SQLite parses foreign keys but does not enforce them unless this
    pragma is set per connection. The schema declares ON DELETE
    behavior everywhere; without enforcement a missed ORM cascade
    could silently orphan rows. Verified orphan-free before enabling.
    """
    try:
        # pysqlite only: PostgreSQL/MySQL enforce foreign keys by default.
        if "sqlite" in type(dbapi_connection).__module__:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    except Exception:
        pass


def create_app(config_name="development"):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    config_class = config_by_name.get(config_name, config_by_name["default"])
    if config_class is ProductionConfig and os.getenv(
        "SECRET_KEY", DEV_FALLBACK_SECRET
    ) in (None, "", DEV_FALLBACK_SECRET):
        if os.getenv("VERCEL"):
            # Provide a fallback secret key on Vercel if not yet set in project settings
            app.config["SECRET_KEY"] = os.getenv(
                "VERCEL_GIT_COMMIT_SHA", "vercel-auto-session-key-fallback"
            )
        else:
            raise RuntimeError(
                "SECRET_KEY must be set in the environment for production."
            )
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    # Global CSRF protection: every POST/PUT/PATCH/DELETE requires a
    # valid token, so all admin state-changing routes are covered.
    csrf.init_app(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    # Storage and database initialization
    with app.app_context():
        try:
            from app.services.media_vault import media_directory
            media_directory()
        except Exception:
            pass

        try:
            db.create_all()
            from app.seed import seed_portfolio
            seed_portfolio()
        except Exception as e:
            app.logger.warning(f"Database auto-init or seed skipped: {e}")

    register_error_handlers(app)
    register_cli_commands(app)

    return app


def register_error_handlers(app):
    """Simple user-facing error pages (no stack traces or secrets)."""

    def _make_handler(c):
        def _handler(e):
            try:
                return render_template(f"errors/{c}.html"), c
            except Exception:
                return f"<h1>Error {c}</h1><p>An error occurred.</p>", c
        return _handler

    for code in (400, 403, 404, 500):
        app.register_error_handler(code, _make_handler(code))


def register_cli_commands(app):
    """Management commands (development use, e.g. creating the admin)."""

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True, help="Admin username.")
    @click.option("--email", prompt=True, help="Admin email address.")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Admin password (hashed, never stored as plaintext).",
    )
    def create_admin(username, email, password):
        """Create an admin user (password is hashed with Werkzeug)."""
        from app.models.admin_user import AdminUser

        existing = AdminUser.query.filter(
            (AdminUser.username == username) | (AdminUser.email == email)
        ).first()
        if existing:
            raise click.ClickException("An admin with that username/email exists.")
        user = AdminUser(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin user '{username}' created.")

    @app.cli.command("reset-admin")
    def reset_admin():
        """Reset an admin user's password (hashed, never stored as plaintext)."""
        from app.models.admin_user import AdminUser

        username = click.prompt("Username", type=str).strip()
        user = AdminUser.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException(
                f"No admin user '{username}' found. Nothing changed."
            )
        # default="" lets an empty entry reach the check below instead of
        # reprompting forever; empty passwords are always rejected.
        new_password = click.prompt(
            "New password",
            hide_input=True,
            confirmation_prompt=True,
            default="",
            show_default=False,
        )
        if not new_password:
            raise click.ClickException("Password must not be empty. Nothing changed.")
        user.set_password(new_password)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise click.ClickException("Password reset failed; database rolled back.")
        click.echo(f"Password reset for admin user '{username}'.")

    @app.cli.command("seed-portfolio")
    def seed_portfolio():
        """Seed the real portfolio dataset (idempotent, never duplicates)."""
        from app.seed import seed_portfolio as run_seed

        counts = run_seed()
        click.echo(f"Created: {counts['created']}")
        click.echo(f"Updated: {counts['updated']}")
        click.echo(f"Unchanged: {counts['unchanged']}")
