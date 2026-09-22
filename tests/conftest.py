"""Shared pytest fixtures and helpers: app, client, admin users."""

import re

import pytest
from flask import g

from app import create_app
from app.models import db
from app.models.admin_user import AdminUser


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        # Runtime SQLite connections enforce FOREIGN KEYs (factory pragma).
        # The documents<->versions circular reference cannot satisfy DROP
        # TABLE ordering, so teardown drops with enforcement paused on this
        # isolated test connection only. Production never runs drop_all.
        db.session.execute(db.text("PRAGMA foreign_keys=OFF"))
        db.drop_all()
        db.session.execute(db.text("PRAGMA foreign_keys=ON"))
        db.session.remove()


class RequestScopedClient:
    """Wrap FlaskClient so `g` behaves like production (per-request).

    The `app` fixture holds a single app context for the whole test so
    tests can use db.session directly. In production each request gets a
    fresh `g`, but here it would persist across requests — leaving e.g.
    Flask-WTF's cached `g.csrf_token` stale after login rotates the
    session, which makes every subsequent POST fail CSRF validation.
    Resetting the request-cached keys before each request reproduces the
    production lifetime.
    """

    def __init__(self, client):
        self._client = client

    def _reset_request_cache(self):
        g.pop("csrf_token", None)
        g.pop("admin_user", None)

    def get(self, *args, **kwargs):
        self._reset_request_cache()
        return self._client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self._reset_request_cache()
        return self._client.post(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._client, name)


@pytest.fixture
def client(app):
    return RequestScopedClient(app.test_client())


def _make_user(username, email, password, is_active=True):
    user = AdminUser(username=username, email=email, is_active=is_active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    return _make_user("admin", "admin@example.com", "correct-password")


@pytest.fixture
def inactive_user(app):
    return _make_user("inactive", "inactive@example.com", "correct-password",
                      is_active=False)


def extract_csrf_token(html):
    """Extract the CSRF token value from rendered page HTML."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "CSRF token not found in page"
    return match.group(1)


def get_csrf_token(client):
    """Extract the session CSRF token from the login page."""
    return extract_csrf_token(client.get("/admin/login").get_data(as_text=True))


def login(client, identifier="admin", password="correct-password"):
    """Log in, returning (response, csrf_token) for reuse in later POSTs.

    A successful login establishes a fresh session, which invalidates
    the pre-login CSRF token — so the token is re-read from the
    dashboard afterwards. Failed logins yield None as the token.
    """
    token = get_csrf_token(client)
    response = client.post(
        "/admin/login",
        data={"identifier": identifier, "password": password, "csrf_token": token},
    )
    fresh_token = None
    dashboard = client.get("/admin/dashboard")
    if dashboard.status_code == 200:
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            dashboard.get_data(as_text=True),
        )
        if match:
            fresh_token = match.group(1)
    return response, fresh_token


def post(client, url, token, data=None, follow_redirects=False):
    payload = dict(data or {})
    payload["csrf_token"] = token
    return client.post(url, data=payload, follow_redirects=follow_redirects)