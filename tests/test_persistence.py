"""Storage persistence tests: files must survive restarts, stay consistent
with their database rows, and never be wiped by anything but an explicit,
reference-checked delete.
"""

import io
import os
import shutil
import uuid

import pytest

from app import create_app
from app.models import db
from app.models.project import Project, ProjectCategory, ProjectMedia
from app.services.media_vault import (
    local_file_exists,
    media_directory,
    storage_status,
)
from tests.conftest import login, post

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 100


@pytest.fixture
def isolated_media(app, tmp_path):
    """A fresh servable media root for this test (inside static).

    Must stay inside the static tree so /static/... URLs resolve; it is
    removed afterwards. Nothing here touches development uploads.
    """
    target = os.path.join(
        app.static_folder, "uploads", f"test-{uuid.uuid4().hex}")
    app.config["MEDIA_ROOT"] = target
    with app.app_context():
        media_directory()
    yield target
    shutil.rmtree(target, ignore_errors=True)


def make_showcase_project(slug="persist-case"):
    category = ProjectCategory.query.filter_by(slug="built").first()
    if category is None:
        category = ProjectCategory(name="Built", slug="built")
        db.session.add(category)
        db.session.flush()
    project = Project(title="Persist Case", slug=slug, status="COMPLETED",
                      category_id=category.id)
    db.session.add(project)
    db.session.commit()
    return project


def upload(client, token, project_id, fields, file=None):
    data = dict(fields)
    data["csrf_token"] = token
    if file is not None:
        content, filename = file
        data["file"] = (io.BytesIO(content), filename)
    return client.post(f"/admin/projects/{project_id}/media", data=data,
                       content_type="multipart/form-data")


def edit(client, token, media_id, fields, file=None):
    data = dict(fields)
    data["csrf_token"] = token
    if file is not None:
        content, filename = file
        data["file"] = (io.BytesIO(content), filename)
    response = client.post(f"/admin/projects/media/{media_id}/edit",
                           data=data, content_type="multipart/form-data")
    db.session.expire_all()
    return response


def meta_fields(**overrides):
    fields = {"media_type": "image", "file_path": "",
              "alt_text": "", "caption": "", "display_order": "0"}
    fields.update(overrides)
    return fields


# ------------------------------------------------------------ upload basics

def test_upload_image_file_exists(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    response = upload(client, token, project.id, meta_fields(),
                      file=(PNG, "shot.png"))
    assert response.status_code == 302
    media = ProjectMedia.query.one()
    assert local_file_exists(media.file_path)
    assert os.path.isfile(os.path.join(app_static(client),
                                       media.file_path))


def app_static(client):
    from flask import current_app

    return current_app.static_folder


def test_upload_video_file_exists(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    fields = meta_fields(media_type="video")
    response = upload(client, token, project.id, fields,
                      file=(MP4, "demo.mp4"))
    assert response.status_code == 302
    media = ProjectMedia.query.one()
    assert media.file_path.endswith(".mp4")
    assert local_file_exists(media.file_path)


def test_database_path_is_canonical_relative(client, admin_user,
                                             isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    assert not media.file_path.startswith("http")
    assert not media.file_path.startswith("/")
    assert ".." not in media.file_path
    assert "\\" not in media.file_path
    assert ":" not in media.file_path
    assert media.browser_url == f"/static/{media.file_path}"


def test_public_url_resolves(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    response = client.get(f"/static/{media.file_path}")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"


# ------------------------------------------------------- restart lifecycle

def _login_token(app_client):
    import re

    from flask import g

    def fresh():
        # Same lifetime rule as tests.conftest: each request gets a
        # fresh g, otherwise the pre-login CSRF cache breaks the POST.
        g.pop("csrf_token", None)
        g.pop("admin_user", None)

    fresh()
    html = app_client.get("/admin/login").get_data(as_text=True)
    token = re.search(
        r'name="csrf_token" value="([^"]+)"', html).group(1)
    from app.models.admin_user import AdminUser

    user = AdminUser(username="root", email="root@example.com")
    user.set_password("correct-password")
    db.session.add(user)
    db.session.commit()
    fresh()
    app_client.post("/admin/login", data={
        "identifier": "root", "password": "correct-password",
        "csrf_token": token})
    fresh()
    dashboard = app_client.get("/admin/dashboard").get_data(as_text=True)
    token = re.search(
        r'name="csrf_token" value="([^"]+)"', dashboard).group(1)
    return fresh, token


def test_restart_lifecycle(tmp_path):
    """UPLOAD -> SAVE -> CLOSE APP -> START APP AGAIN -> MEDIA LOADS."""
    import config as config_module

    file_uri = "sqlite:///" + str(tmp_path / "restart.db").replace(
        "\\", "/")
    original_uri = config_module.TestingConfig.SQLALCHEMY_DATABASE_URI
    config_module.TestingConfig.SQLALCHEMY_DATABASE_URI = file_uri
    try:
        media_root = os.path.join(
            create_app("testing").static_folder, "uploads",
            f"restart-{uuid.uuid4().hex}")
        first = create_app("testing")
        first.config["MEDIA_ROOT"] = media_root
        with first.app_context():
            db.create_all()
            browser_url = None
            slug = "restart-case"
            with first.test_client() as web:
                fresh, token = _login_token(web)
                project = Project(title="Restart", slug=slug,
                                  status="COMPLETED")
                db.session.add(project)
                db.session.commit()
                data = dict(meta_fields(media_type="video"),
                            csrf_token=token,
                            file=(io.BytesIO(MP4), "clip.mp4"))
                fresh()
                assert web.post(f"/admin/projects/{project.id}/media",
                                data=data,
                                content_type="multipart/form-data"
                                ).status_code == 302
                media = ProjectMedia.query.one()
                browser_url = f"/static/{media.file_path}"
                assert os.path.isfile(os.path.join(
                    first.static_folder, media.file_path))
                fresh()
                assert web.get(browser_url).status_code == 200
            db.session.remove()
            db.engine.dispose()
        del first
        # Fresh process-equivalent: brand-new app object, same storage.
        second = create_app("testing")
        second.config["MEDIA_ROOT"] = media_root
        try:
            with second.app_context():
                assert ProjectMedia.query.count() == 1
                assert local_file_exists(
                    ProjectMedia.query.one().file_path)
            with second.test_client() as web:
                assert web.get(browser_url).status_code == 200
                html = web.get(f"/work/{slug}").get_data(as_text=True)
                assert browser_url in html
        finally:
            with second.app_context():
                db.session.remove()
                db.engine.dispose()
            shutil.rmtree(media_root, ignore_errors=True)
    finally:
        config_module.TestingConfig.SQLALCHEMY_DATABASE_URI = original_uri


# --------------------------------------------------------- missing + replace

def test_missing_file_detected_and_flagged(client, admin_user,
                                           isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    assert storage_status(media.file_path) == "PRESENT"
    os.remove(os.path.join(app_static(client), media.file_path))
    db.session.expire_all()
    assert storage_status(
        ProjectMedia.query.one().file_path) == "MISSING"
    html = client.get(
        f"/admin/projects/{project.id}").get_data(as_text=True)
    assert "MEDIA FILE MISSING" in html


def test_missing_file_does_not_crash_public_page(client, admin_user,
                                                 isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    os.remove(os.path.join(app_static(client), media.file_path))
    response = client.get(f"/work/{project.slug}")
    assert response.status_code == 200


def test_replacement_restores_missing_media(client, admin_user,
                                            isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    old_path = media.file_path
    os.remove(os.path.join(app_static(client), old_path))
    response = edit(client, token, media.id, meta_fields(),
                    file=(PNG, "replacement.png"))
    assert response.status_code == 302
    media = db.session.get(ProjectMedia, media.id)
    assert media is not None
    assert media.project_id == project.id
    assert media.file_path != old_path
    assert local_file_exists(media.file_path)
    assert db.session.get(Project, project.id).media[0].id == media.id


def test_remote_url_still_works(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id,
           meta_fields(file_path="https://example.com/remote.png"))
    media = ProjectMedia.query.one()
    assert storage_status(media.file_path) == "REMOTE"
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert 'src="https://example.com/remote.png"' in html


# --------------------------------------------------------------- deletion

def test_delete_removes_record_and_file(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    disk = os.path.join(app_static(client), media.file_path)
    assert os.path.isfile(disk)
    response = post(client, f"/admin/projects/media/{media.id}/delete",
                    token)
    assert response.status_code == 302
    assert db.session.get(ProjectMedia, media.id) is None
    assert not os.path.exists(disk)


def test_delete_keeps_file_with_other_references(client, admin_user,
                                                 isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(), file=(PNG, "shot.png"))
    media = ProjectMedia.query.one()
    db.session.add(ProjectMedia(project_id=project.id, media_type="image",
                                file_path=media.file_path))
    db.session.commit()
    disk = os.path.join(app_static(client), media.file_path)
    post(client, f"/admin/projects/media/{media.id}/delete", token)
    assert os.path.isfile(disk)


# ----------------------------------------------------------------- failures

def test_failed_upload_creates_no_record(client, admin_user,
                                         isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    before = set(os.listdir(isolated_media))
    response = upload(client, token, project.id, meta_fields(),
                      file=(b"plain text, not a png", "shot.png"))
    assert response.status_code == 302
    assert ProjectMedia.query.count() == 0
    assert set(os.listdir(isolated_media)) == before


def test_failed_commit_leaves_no_orphan(client, admin_user, isolated_media,
                                        monkeypatch):
    project = make_showcase_project()
    _, token = login(client)
    before = set(os.listdir(isolated_media))

    def boom():
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(db.session, "commit", boom)
    response = upload(client, token, project.id, meta_fields(),
                      file=(PNG, "shot.png"))
    assert response.status_code == 302
    assert ProjectMedia.query.count() == 0
    assert set(os.listdir(isolated_media)) == before


def test_traversal_filename_neutralized(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    response = upload(client, token, project.id, meta_fields(),
                      file=(PNG, "../../evil.png"))
    assert response.status_code == 302
    media = ProjectMedia.query.one()
    assert ".." not in media.file_path
    assert local_file_exists(media.file_path)


def test_traversal_path_rejected(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    response = upload(client, token, project.id,
                      meta_fields(file_path="../secret/x.png"))
    assert response.status_code == 302
    assert ProjectMedia.query.count() == 0


def test_unsupported_upload_rejected(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    before = set(os.listdir(isolated_media))
    response = upload(client, token, project.id, meta_fields(),
                      file=(b"<?php evil();", "shell.php"))
    assert response.status_code == 302
    assert ProjectMedia.query.count() == 0
    assert set(os.listdir(isolated_media)) == before


def test_video_range_requests(client, admin_user, isolated_media):
    project = make_showcase_project()
    _, token = login(client)
    upload(client, token, project.id, meta_fields(media_type="video"),
           file=(MP4, "demo.mp4"))
    media = ProjectMedia.query.one()
    response = client.get(f"/static/{media.file_path}",
                          headers={"Range": "bytes=0-11"})
    assert response.status_code == 206
    assert response.headers["Content-Range"] == f"bytes 0-11/{len(MP4)}"
    assert response.headers["Content-Type"] == "video/mp4"
    assert response.data == MP4[:12]
