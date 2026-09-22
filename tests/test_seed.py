"""Seed tests: dataset creation, idempotency, public rendering, safety."""

from app.models import db
from app.models.crm import Contact, Lead
from app.models.experience import Experience
from app.models.learning import LearningItem
from app.models.project import Project, ProjectCategory, ProjectLink
from app.seed import seed_portfolio
from tests.conftest import login

SEED_SLUGS = ["estora", "umama-motors", "business-systems", "clh-wp",
              "autonomous-economic-agent"]


def test_seed_creates_categories(app):
    seed_portfolio()
    assert ProjectCategory.query.filter_by(slug="built").one().name == "Built"
    assert ProjectCategory.query.filter_by(slug="r-and-d").one().name == "R&D"


def test_seed_creates_projects(app):
    seed_portfolio()
    slugs = {p.slug for p in Project.query.all()}
    assert set(SEED_SLUGS).issubset(slugs)
    estora = Project.query.filter_by(slug="estora").one()
    assert estora.title == "Estora"
    assert estora.status == "COMPLETED"
    assert estora.is_featured is True


def test_seed_creates_experiences(app):
    seed_portfolio()
    vespera = Experience.query.filter_by(organization="Vespera Estates").one()
    assert "friction" in vespera.description


def test_seed_creates_learning_items(app):
    seed_portfolio()
    titles = {i.title for i in LearningItem.query.all()}
    assert {"C", "Python", "SQL / databases",
            "Web application architecture"}.issubset(titles)


def test_seed_creates_project_links(app):
    seed_portfolio()
    estora = Project.query.filter_by(slug="estora").one()
    assert "https://estora-2y3m.onrender.com/" in [link.url for link in estora.links]
    umama = Project.query.filter_by(slug="umama-motors").one()
    assert "https://github.com/Hanzalaq/umama-motors" in [link.url for link in umama.links]


def test_seed_is_idempotent(app):
    seed_portfolio()
    counts = seed_portfolio()
    assert counts["created"] == 0
    assert counts["updated"] == 0
    assert counts["unchanged"] > 0


def test_seed_creates_no_duplicate_projects(app):
    seed_portfolio()
    seed_portfolio()
    for slug in SEED_SLUGS:
        assert Project.query.filter_by(slug=slug).count() == 1


def test_seed_creates_no_duplicate_categories(app):
    seed_portfolio()
    seed_portfolio()
    assert ProjectCategory.query.filter_by(slug="built").count() == 1
    assert ProjectCategory.query.filter_by(slug="r-and-d").count() == 1


def test_seeded_projects_render_publicly(client):
    seed_portfolio()
    html = client.get("/work").get_data(as_text=True)
    for title in ["Estora", "Umama Motors", "CLH.WP"]:
        assert title in html
    assert "Estora" in client.get("/").get_data(as_text=True)


def test_seeded_project_detail_pages_render(client):
    seed_portfolio()
    for slug in SEED_SLUGS:
        response = client.get(f"/work/{slug}")
        assert response.status_code == 200, slug
    html = client.get("/work/estora").get_data(as_text=True)
    assert "property management" in html
    assert "Limitations" in html  # honest limitations section renders


def test_seeded_project_links_render(client):
    seed_portfolio()
    html = client.get("/work/estora").get_data(as_text=True)
    assert "https://estora-2y3m.onrender.com/" in html
    html = client.get("/work/umama-motors").get_data(as_text=True)
    assert "https://github.com/Hanzalaq/umama-motors" in html


def test_rd_statuses_render_correctly(client):
    seed_portfolio()
    assert "BETA" in client.get("/work/clh-wp").get_data(as_text=True)
    assert "PLANNING" in client.get("/work/autonomous-economic-agent").get_data(as_text=True)


def test_seed_preserves_crm_data(app):
    contact = Contact(name="Keep Me", email="keep@example.com", message="Hi")
    db.session.add(contact)
    db.session.flush()
    db.session.add(Lead(contact_id=contact.id, status="QUALIFIED"))
    db.session.commit()
    seed_portfolio()
    seed_portfolio()
    assert Contact.query.filter_by(email="keep@example.com").count() == 1
    assert Lead.query.filter_by(status="QUALIFIED").count() == 1


def test_seeded_content_visible_in_admin(client, admin_user):
    seed_portfolio()
    login(client)
    html = client.get("/admin/projects").get_data(as_text=True)
    assert "Estora" in html
    assert "CLH.WP" in html
    assert client.get("/admin/categories").status_code == 200


def test_seed_preserves_unrelated_records(app):
    manual = Project(title="Manual", slug="manual", status="COMPLETED")
    db.session.add(manual)
    db.session.commit()
    seed_portfolio()
    surviving = Project.query.filter_by(slug="manual").one()
    assert surviving.title == "Manual"
    assert Project.query.count() == len(SEED_SLUGS) + 1
