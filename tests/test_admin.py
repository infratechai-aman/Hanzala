"""Admin panel tests: auth, CSRF, CRUD, links/media, dashboard."""

from app.models import db
from app.models.crm import Client, Contact, Lead
from app.models.project import Project, ProjectCategory, ProjectLink, ProjectMedia
from tests.conftest import get_csrf_token, login, post


def make_category(name="Built", slug="built"):
    category = ProjectCategory(name=name, slug=slug)
    db.session.add(category)
    db.session.commit()
    return category


def project_data(**overrides):
    data = {"title": "Case Study", "slug": "case-study", "status": "COMPLETED"}
    data.update(overrides)
    return data


# ------------------------------------------------------------------ auth

def test_login_page_loads(client):
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert b"name=\"password\"" in response.data


def test_valid_login(client, admin_user):
    response, _ = login(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
    with client.session_transaction() as session:
        assert session.get("admin_user_id") == admin_user.id


def test_invalid_password_fails(client, admin_user):
    response, _ = login(client, password="wrong-password")
    assert response.status_code == 200
    assert b"Invalid credentials." in response.data
    with client.session_transaction() as session:
        assert session.get("admin_user_id") is None


def test_inactive_admin_cannot_login(client, inactive_user):
    response, _ = login(client, identifier="inactive")
    assert response.status_code == 200
    assert b"Invalid credentials." in response.data
    with client.session_transaction() as session:
        assert session.get("admin_user_id") is None


def test_dashboard_requires_auth(client):
    response = client.get("/admin/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")


def test_authenticated_dashboard(client, admin_user):
    login(client)
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_logout(client, admin_user):
    _, token = login(client)
    response = post(client, "/admin/logout", token)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")
    assert client.get("/admin/dashboard").status_code == 302


# ------------------------------------------------------------------ CSRF

def test_state_changes_require_csrf(client, admin_user):
    # Anonymous login attempt without a token.
    response = client.post(
        "/admin/login", data={"identifier": "admin", "password": "x"}
    )
    assert response.status_code == 400

    # Authenticated project creation without a token.
    login(client)
    response = client.post("/admin/projects/new", data=project_data())
    assert response.status_code == 400


# --------------------------------------------------------------- projects

def test_create_project(client, admin_user):
    _, token = login(client)
    response = post(client, "/admin/projects/new", token, project_data())
    assert response.status_code == 302
    project = Project.query.filter_by(slug="case-study").one()
    assert project.title == "Case Study"


def test_edit_project(client, admin_user):
    _, token = login(client)
    post(client, "/admin/projects/new", token, project_data())
    project = Project.query.filter_by(slug="case-study").one()

    response = post(
        client,
        f"/admin/projects/{project.id}/edit",
        token,
        project_data(title="Updated Title"),
    )
    assert response.status_code == 302
    assert db.session.get(Project, project.id).title == "Updated Title"


def test_delete_project(client, admin_user):
    _, token = login(client)
    post(client, "/admin/projects/new", token, project_data())
    project = Project.query.filter_by(slug="case-study").one()

    # GET must not delete (route only allows POST).
    assert client.get(f"/admin/projects/{project.id}/delete").status_code == 405

    response = post(client, f"/admin/projects/{project.id}/delete", token)
    assert response.status_code == 302
    assert db.session.get(Project, project.id) is None


def test_duplicate_project_slug_rejected(client, admin_user):
    _, token = login(client)
    post(client, "/admin/projects/new", token, project_data())
    response = post(
        client, "/admin/projects/new", token, project_data(title="Different")
    )
    assert response.status_code == 200
    assert b"already in use" in response.data
    assert Project.query.filter_by(slug="case-study").count() == 1
    assert Project.query.filter_by(slug="case-study").one().title == "Case Study"


def test_unauthenticated_project_modification_rejected(client, admin_user):
    token = get_csrf_token(client)  # valid token, but no login
    assert post(client, "/admin/projects/new", token, project_data()).status_code == 302

    project = Project(title="P", slug="p", status="COMPLETED")
    db.session.add(project)
    db.session.commit()

    edit = post(
        client, f"/admin/projects/{project.id}/edit", token, project_data()
    )
    delete = post(client, f"/admin/projects/{project.id}/delete", token)
    assert edit.status_code == 302
    assert edit.headers["Location"].endswith("/admin/login")
    assert delete.status_code == 302
    assert Project.query.count() == 1  # only the fixture project exists


# ------------------------------------------------------------- categories

def test_create_category(client, admin_user):
    _, token = login(client)
    response = post(
        client, "/admin/categories/new", token,
        {"name": "Built", "slug": "built", "description": "Shipped work"},
    )
    assert response.status_code == 302
    assert ProjectCategory.query.filter_by(slug="built").one().name == "Built"


def test_edit_category(client, admin_user):
    make_category()
    category = ProjectCategory.query.filter_by(slug="built").one()
    _, token = login(client)
    response = post(
        client, f"/admin/categories/{category.id}/edit", token,
        {"name": "R&D", "slug": "rnd", "description": ""},
    )
    assert response.status_code == 302
    updated = db.session.get(ProjectCategory, category.id)
    assert (updated.name, updated.slug) == ("R&D", "rnd")


def test_delete_category(client, admin_user):
    make_category()
    category = ProjectCategory.query.filter_by(slug="built").one()
    _, token = login(client)
    response = post(client, f"/admin/categories/{category.id}/delete", token)
    assert response.status_code == 302
    assert db.session.get(ProjectCategory, category.id) is None


def test_delete_category_preserves_projects(client, admin_user):
    category = make_category()
    project = Project(title="P", slug="p", status="COMPLETED", category=category)
    db.session.add(project)
    db.session.commit()

    _, token = login(client)
    post(client, f"/admin/categories/{category.id}/delete", token)

    surviving = db.session.get(Project, project.id)
    assert surviving is not None
    assert surviving.category_id is None


# ------------------------------------------------------------ links/media

def test_project_links_crud(client, admin_user):
    _, token = login(client)
    post(client, "/admin/projects/new", token, project_data())
    project = Project.query.filter_by(slug="case-study").one()

    # Create.
    response = post(
        client, f"/admin/projects/{project.id}/links", token,
        {"label": "Live Demo", "url": "https://example.com", "link_type": "demo",
         "display_order": "0"},
    )
    assert response.status_code == 302
    link = ProjectLink.query.filter_by(project_id=project.id).one()
    assert link.url == "https://example.com"

    # Unsafe URL rejected.
    bad = post(
        client, f"/admin/projects/{project.id}/links", token,
        {"label": "X", "url": "javascript:alert(1)", "link_type": "",
         "display_order": "0"},
    )
    assert bad.status_code == 302
    assert ProjectLink.query.filter_by(project_id=project.id).count() == 1

    # Update.
    post(
        client, f"/admin/projects/links/{link.id}/edit", token,
        {"label": "GitHub", "url": "https://github.com/example", "link_type": "code",
         "display_order": "1"},
    )
    assert db.session.get(ProjectLink, link.id).label == "GitHub"

    # Delete.
    post(client, f"/admin/projects/links/{link.id}/delete", token)
    assert ProjectLink.query.filter_by(project_id=project.id).count() == 0


def test_project_media_metadata_crud(client, admin_user):
    _, token = login(client)
    post(client, "/admin/projects/new", token, project_data())
    project = Project.query.filter_by(slug="case-study").one()

    def media_payload(**overrides):
        payload = {
            "media_type": "image", "file_path": "images/demo.png",
            "alt_text": "Demo", "caption": "", "display_order": "0",
        }
        payload.update(overrides)
        return payload

    # Create.
    response = post(
        client, f"/admin/projects/{project.id}/media", token, media_payload()
    )
    assert response.status_code == 302
    media = ProjectMedia.query.filter_by(project_id=project.id).one()
    assert media.file_path == "images/demo.png"

    # Path traversal rejected.
    bad = post(
        client, f"/admin/projects/{project.id}/media", token,
        media_payload(file_path="../secret.txt"),
    )
    assert bad.status_code == 302
    assert ProjectMedia.query.filter_by(project_id=project.id).count() == 1

    # Update.
    post(
        client, f"/admin/projects/media/{media.id}/edit", token,
        media_payload(file_path="images/updated.png", caption="New caption"),
    )
    updated = db.session.get(ProjectMedia, media.id)
    assert updated.file_path == "images/updated.png"
    assert updated.caption == "New caption"

    # Delete.
    post(client, f"/admin/projects/media/{media.id}/delete", token)
    assert ProjectMedia.query.filter_by(project_id=project.id).count() == 0


# -------------------------------------------------------------- dashboard

def test_dashboard_stats_reflect_records(client, admin_user):
    make_category()
    category = ProjectCategory.query.first()
    db.session.add_all([
        Project(title="A", slug="a", status="COMPLETED", category=category),
        Project(title="B", slug="b", status="PROTOTYPE"),
    ])
    contact = Contact(name="Jane", email="jane@example.com")
    lead = Lead(contact=contact, status="LEAD")
    client_obj = Client(contact=contact, company="Acme")
    db.session.add_all([contact, lead, client_obj])
    db.session.commit()

    login(client)
    html = client.get("/admin/dashboard").get_data(as_text=True)
    for heading in ("Overview", "Lead pipeline", "Recent leads",
                    "Recent projects", "Documents"):
        assert heading in html
    assert "dt>LEAD</dt><dd>1</dd>" in html
    assert "dt>Total</dt><dd>0</dd>" in html
    assert "Nothing requires attention." in html
    assert "Jane" in html
    assert f"/admin/crm/leads/{lead.id}" in html
    assert ">A<" in html and ">B<" in html
