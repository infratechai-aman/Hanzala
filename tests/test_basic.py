"""Minimal smoke test: the app starts and / returns HTTP 200."""

import pytest

from app import create_app


def test_index_returns_200(app):
    # Uses the shared `app` fixture so database tables exist: the
    # homepage now queries them.
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")
