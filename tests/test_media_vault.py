"""Media Vault tests: auth, CRUD, validation, visibility, uploads,
intro placement, ordering, and audit guards (FK pragma, prod secret)."""

import io
from unittest import mock

import pytest

from app.models import db
from app.models.media_vault import PortfolioMedia
from app.models.project import Project, ProjectMedia
from tests.conftest import get_csrf_token, login, post

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 100


@pytest.fixture(autouse=True)
def clean_media_dir(app):
    """Remove only files this test created, never pre-existing uploads.

    The test app shares the real media directory, so a blind wipe would
    destroy development uploads whose database rows survive — exactly a
    record-survives/file-404 incident. Snapshot before, delete only the
    newcomers after.
    """
    import os

    from app.services.media_vault import media_directory

    with app.app_context():
        before = set(os.listdir(media_directory()))
    yield
    with app.app_context():
        path = media_directory()
        for entry in os.listdir(path):
            if entry in before:
                continue
            full = os.path.join(path, entry)
            if os.path.isfile(full):
                os.remove(full)


def vault_post(client, url, token, fields, file=None):
    data = dict(fields)
    data["csrf_token"] = token
    if file is not None:
        content, filename = file
        data["file"] = (io.BytesIO(content), filename)
    return client.post(url, data=data, content_type="multipart/form-data")


def external_fields(**overrides):
    fields = {
        "title": "Intro video",
        "caption": "Hello",
        "media_type": "EXTERNAL_URL",
        "source": "external",
        "external_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "alt_text": "Intro",
        "poster": "",
        "context": "INTRO",
        "project_id": "",
        "visibility": "PUBLISHED",
        "display_order": "0",
    }
    fields.update(overrides)
    return fields


def make_item(**overrides):
    fields = {
        "title": "Asset",
        "media_type": "EXTERNAL_URL",
        "storage": "EXTERNAL",
        "location": "https://example.com/a.mp4",
        "context": "WORK",
        "visibility": "DRAFT",
        "display_order": 0,
    }
    fields.update(overrides)
    item = PortfolioMedia(**fields)
    db.session.add(item)
    db.session.commit()
    return item


# ------------------------------------------------------- auth gates

def test_media_list_requires_auth(client, admin_user):
    make_item()
    assert client.get("/admin/media").status_code == 302


def test_media_create_requires_auth(client, admin_user):
    make_item()
    token = get_csrf_token(client)
    response = vault_post(client, "/admin/media/new", token,
                          external_fields())
    assert response.status_code == 302
    assert PortfolioMedia.query.count() == 1


def test_media_new_requires_auth_get(client, admin_user):
    assert client.get("/admin/media/new").status_code == 302


# ------------------------------------------------------------- CRUD

def test_media_create_works(client, admin_user):
    _, token = login(client)
    response = vault_post(client, "/admin/media/new", token,
                          external_fields())
    assert response.status_code == 302
    item = PortfolioMedia.query.one()
    assert (item.title, item.visibility) == ("Intro video", "PUBLISHED")


def test_media_edit_works(client, admin_user):
    item = make_item()
    _, token = login(client)
    fields = external_fields(title="Renamed", visibility="DRAFT",
                             context="WORK")
    response = vault_post(client, f"/admin/media/{item.id}/edit", token,
                          fields)
    assert response.status_code == 302
    assert db.session.get(PortfolioMedia, item.id).title == "Renamed"


def test_media_delete_requires_post(client, admin_user):
    item = make_item()
    login(client)
    assert client.get(f"/admin/media/{item.id}/delete").status_code == 405
    assert db.session.get(PortfolioMedia, item.id) is not None


def test_media_delete_requires_csrf(client, admin_user):
    item = make_item()
    login(client)
    assert client.post(f"/admin/media/{item.id}/delete").status_code == 400
    assert db.session.get(PortfolioMedia, item.id) is not None


def test_media_delete_removes_row(client, admin_user):
    item = make_item()
    _, token = login(client)
    response = post(client, f"/admin/media/{item.id}/delete", token)
    assert response.status_code == 302
    assert db.session.get(PortfolioMedia, item.id) is None


# ------------------------------------------------------- visibility

def test_draft_not_public(client, admin_user):
    make_item(visibility="DRAFT", context="INTRO")
    assert "intro-heading" not in client.get("/").get_data(as_text=True)


def test_published_intro_public(client, admin_user):
    make_item(visibility="PUBLISHED", context="INTRO")
    html = client.get("/").get_data(as_text=True)
    assert "intro-heading" in html
    assert "example.com" in html


def test_archived_not_public(client, admin_user):
    make_item(visibility="ARCHIVED", context="INTRO")
    assert "intro-heading" not in client.get("/").get_data(as_text=True)


def test_no_video_no_section(client):
    assert "intro-heading" not in client.get("/").get_data(as_text=True)


def test_youtube_embed_allowlisted(client, admin_user):
    make_item(visibility="PUBLISHED", context="INTRO",
              location="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    html = client.get("/").get_data(as_text=True)
    assert "youtube.com/embed/dQw4w9WgXcQ" in html


def test_generic_url_renders_link_not_iframe(client, admin_user):
    make_item(visibility="PUBLISHED", context="INTRO",
              location="https://example.com/video.mp4")
    html = client.get("/").get_data(as_text=True)
    assert "<iframe" not in html
    assert "example.com/video.mp4" in html


# ------------------------------------------------------- validation

def test_invalid_media_type_rejected(client, admin_user):
    _, token = login(client)
    response = vault_post(client, "/admin/media/new", token,
                          external_fields(media_type="NOPE"))
    assert response.status_code == 200
    assert PortfolioMedia.query.count() == 0


def test_invalid_external_url_rejected(client, admin_user):
    _, token = login(client)
    response = vault_post(
        client, "/admin/media/new", token,
        external_fields(external_url="javascript:alert(1)"))
    assert response.status_code == 200
    assert PortfolioMedia.query.count() == 0


def test_unsafe_extension_rejected(client, admin_user):
    _, token = login(client)
    fields = external_fields(media_type="IMAGE", source="upload",
                             external_url="")
    fields = {**fields, "media_type": "IMAGE"}
    response = vault_post(client, "/admin/media/new", token, fields,
                          file=(b"<?php evil();", "shell.php"))
    assert response.status_code == 200
    assert PortfolioMedia.query.count() == 0


def test_magic_mismatch_rejected(client, admin_user):
    _, token = login(client)
    fields = external_fields(media_type="IMAGE", source="upload",
                             external_url="")
    response = vault_post(client, "/admin/media/new", token, fields,
                          file=(b"plain text, not a png", "shot.png"))
    assert response.status_code == 200
    assert PortfolioMedia.query.count() == 0


def test_oversized_file_rejected(client, admin_user):
    _, token = login(client)
    fields = external_fields(media_type="IMAGE", source="upload",
                             external_url="")
    with mock.patch("app.services.media_vault.MAX_FILE_SIZE", 10):
        response = vault_post(client, "/admin/media/new", token, fields,
                              file=(PNG, "shot.png"))
    assert response.status_code == 200
    assert PortfolioMedia.query.count() == 0


def test_traversal_filename_neutralized(client, admin_user, tmp_path):
    _, token = login(client)
    fields = dict(external_fields(media_type="IMAGE", source="upload",
                                  external_url="", context="WORK",
                                  visibility="DRAFT"))
    response = vault_post(client, "/admin/media/new", token, fields,
                          file=(PNG, "../../evil.png"))
    assert response.status_code == 302
    item = PortfolioMedia.query.one()
    assert ".." not in item.location
    assert "/" not in item.location.split("uploads/media/")[-1].replace(
        ".png", "")
    assert item.location.startswith("uploads/media/")
    assert item.location.endswith(".png")


def test_local_upload_roundtrip_and_delete(client, admin_user):
    import os

    from flask import current_app

    _, token = login(client)
    fields = dict(external_fields(media_type="VIDEO", source="upload",
                                  external_url="", context="WORK",
                                  visibility="DRAFT"))
    response = vault_post(client, "/admin/media/new", token, fields,
                          file=(MP4, "demo.mp4"))
    assert response.status_code == 302
    item = PortfolioMedia.query.one()
    assert item.storage == "LOCAL"
    disk = os.path.join(current_app.static_folder, item.location)
    assert os.path.isfile(disk)
    post(client, f"/admin/media/{item.id}/delete", token)
    assert not os.path.exists(disk)


def test_project_context_requires_project(client, admin_user):
    _, token = login(client)
    response = vault_post(
        client, "/admin/media/new", token,
        external_fields(context="PROJECT", project_id="",
                        visibility="DRAFT"))
    assert response.status_code == 200
    assert PortfolioMedia.query.count() == 0


# -------------------------------------------------- intro uniqueness

def test_second_published_intro_blocked(client, admin_user):
    make_item(visibility="PUBLISHED", context="INTRO")
    _, token = login(client)
    response = vault_post(client, "/admin/media/new", token,
                          external_fields(title="Second"))
    assert response.status_code == 200
    assert PortfolioMedia.query.filter_by(
        visibility="PUBLISHED", context="INTRO").count() == 1


def test_intro_visibility_switch_guarded(client, admin_user):
    first = make_item(visibility="PUBLISHED", context="INTRO")
    second = make_item(title="Second", visibility="DRAFT", context="INTRO")
    _, token = login(client)
    post(client, f"/admin/media/{second.id}/visibility", token,
         {"visibility": "PUBLISHED"})
    assert db.session.get(PortfolioMedia, second.id).visibility == "DRAFT"
    post(client, f"/admin/media/{first.id}/visibility", token,
         {"visibility": "ARCHIVED"})
    post(client, f"/admin/media/{second.id}/visibility", token,
         {"visibility": "PUBLISHED"})
    assert db.session.get(PortfolioMedia, second.id).visibility == "PUBLISHED"


def test_intro_uniqueness_enforced_by_database(app):
    """Partial unique index: two published INTROs fail even bypassing app."""
    from sqlalchemy.exc import IntegrityError

    make_item(visibility="PUBLISHED", context="INTRO")
    db.session.add(PortfolioMedia(
        title="Sneaky", media_type="EXTERNAL_URL", storage="EXTERNAL",
        location="https://example.com/b.mp4", context="INTRO",
        visibility="PUBLISHED", display_order=0))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_ordering(client, admin_user):
    make_item(title="B", visibility="PUBLISHED", context="HOME",
              display_order=2)
    make_item(title="A", visibility="PUBLISHED", context="HOME",
              display_order=1)
    _, token = login(client)
    assert token is not None
    from app.services.media_vault import published_for_context

    assert [i.title for i in published_for_context("HOME")] == ["A", "B"]


# ------------------------------------------------- project media intact

def test_project_media_still_works(client, admin_user):
    project = Project(title="P", slug="p", status="COMPLETED")
    db.session.add(project)
    db.session.commit()
    _, token = login(client)
    response = post(
        client, f"/admin/projects/{project.id}/media", token,
        {"media_type": "image", "file_path": "images/shot.png",
         "alt_text": "", "caption": "", "display_order": "0"})
    assert response.status_code == 302
    assert ProjectMedia.query.filter_by(project_id=project.id).count() == 1


# ------------------------------------------------------ audit guards

def test_sqlite_fk_enforcement_active(app):
    with app.app_context():
        value = db.session.execute(
            db.text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_production_rejects_dev_fallback_secret(monkeypatch):
    from app import create_app

    monkeypatch.setenv("SECRET_KEY", "dev-only-change-me")
    with pytest.raises(RuntimeError):
        create_app("production")


def test_vault_integrity_helper(app):
    from app.services.media_vault import check_integrity

    with app.app_context():
        assert check_integrity() == []
