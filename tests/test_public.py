"""Public portfolio tests: pages, DB-driven content, privacy."""

from app.models import db
from app.models.admin_user import AdminUser
from app.models.crm import Client, Contact, Lead
from app.models.project import Project, ProjectCategory, ProjectLink


def make_project(slug="db-driven-case", title="DB Driven Case", **overrides):
    category = ProjectCategory.query.filter_by(slug="built").first()
    if category is None:
        category = ProjectCategory(name="Built", slug="built")
        db.session.add(category)
    fields = {
        "title": title,
        "slug": slug,
        "status": "COMPLETED",
        "short_description": "Marker short description 7f3a.",
        "result": "Marker result 7f3a.",
        "category": category,
    }
    fields.update(overrides)
    project = Project(**fields)
    db.session.add(project)
    db.session.commit()
    return project


def test_homepage_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hanzala" in response.data


def test_work_page_returns_200(client):
    assert client.get("/work").status_code == 200


def test_project_detail_loads_existing_project(client):
    make_project()
    response = client.get("/work/db-driven-case")
    assert response.status_code == 200
    assert b"DB Driven Case" in response.data
    assert b"Marker short description 7f3a." in response.data


def test_project_detail_hides_empty_sections(client):
    make_project()
    html = client.get("/work/db-driven-case").get_data(as_text=True)
    # `result` exists so Result renders; untouched fields must not.
    assert "Result" in html
    assert "Limitations" not in html
    assert "Decisions" not in html


def test_invalid_project_slug_returns_404(client):
    assert client.get("/work/no-such-project").status_code == 404


def test_context_page_returns_200(client):
    assert client.get("/context").status_code == 200


def test_learning_page_returns_200(client):
    assert client.get("/learning").status_code == 200


def test_process_page_returns_200(client):
    assert client.get("/process").status_code == 200


def test_contact_page_returns_200(client):
    response = client.get("/contact")
    assert response.status_code == 200
    assert b"Start a project" in response.data


def test_public_content_comes_from_database(client):
    # The homepage first row is pinned to seeded projects; the work index
    # and detail pages reflect arbitrary database content.
    make_project()
    assert b"DB Driven Case" in client.get("/work").get_data()
    assert b"DB Driven Case" in client.get("/work/db-driven-case").get_data()

    # Simulate an admin edit: the public pages must reflect the change
    # with no template or code edits.
    project = Project.query.filter_by(slug="db-driven-case").one()
    project.title = "Edited Public Title 9c1e"
    db.session.commit()
    html = client.get("/work/db-driven-case").get_data(as_text=True)
    assert "Edited Public Title 9c1e" in html
    assert "DB Driven Case" not in html
    assert "Edited Public Title 9c1e" in client.get("/work").get_data(as_text=True)


def test_private_information_not_exposed(client):
    admin = AdminUser(username="secret-admin-e4b2", email="secret-admin-e4b2@example.com")
    admin.set_password("password")
    contact = Contact(
        name="Private Person",
        email="private-contact-e4b2@example.com",
        message="Private message e4b2.",
        company="Private Co e4b2",
    )
    lead = Lead(contact=contact, status="LEAD", notes="Lead notes e4b2.")
    client_obj = Client(contact=contact, company="Private Co e4b2")
    db.session.add_all([admin, contact, lead, client_obj])
    project = make_project()
    project.links = [ProjectLink(label="L", url="https://example.com")]
    db.session.commit()

    pages = ["/", "/work", "/work/db-driven-case", "/context",
             "/learning", "/process", "/contact"]
    for page in pages:
        html = client.get(page).get_data(as_text=True)
        assert "secret-admin-e4b2" not in html
        assert "private-contact-e4b2" not in html
        assert "Private message e4b2" not in html
        assert "Private Co e4b2" not in html
        assert "Lead notes e4b2" not in html
        assert "password_hash" not in html
        assert admin.password_hash not in html
