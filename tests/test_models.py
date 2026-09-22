"""Database foundation tests: schema, hashing, relationships, constraints."""

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

import pytest

from app.models import db
from app.models.admin_user import AdminUser
from app.models.crm import Client, Contact, Lead
from app.models.project import Project, ProjectCategory, ProjectLink

EXPECTED_TABLES = {
    "admin_users",
    "project_categories",
    "projects",
    "project_links",
    "project_media",
    "experiences",
    "learning_items",
    "contacts",
    "leads",
    "clients",
    "followups",
    "notes",
}


def test_database_initializes_and_tables_exist(app):
    tables = set(inspect(db.engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_admin_password_hashing(app):
    user = AdminUser(username="admin", email="admin@example.com")
    user.set_password("s3cret-password")
    db.session.add(user)
    db.session.commit()

    assert user.password_hash != "s3cret-password"
    assert user.check_password("s3cret-password") is True
    assert user.check_password("wrong-password") is False


def test_project_category_relationship(app):
    category = ProjectCategory(name="Built", slug="built")
    project = Project(title="Case Study", slug="case-study", category=category)
    db.session.add_all([category, project])
    db.session.commit()

    assert project.category.name == "Built"
    assert project in category.projects


def test_project_links_relationship_and_cascade(app):
    project = Project(title="Linked", slug="linked")
    project.links = [
        ProjectLink(label="Live Demo", url="https://example.com"),
        ProjectLink(label="GitHub", url="https://github.com/example"),
    ]
    db.session.add(project)
    db.session.commit()
    project_id = project.id

    assert len(project.links) == 2

    db.session.delete(project)
    db.session.commit()
    assert ProjectLink.query.filter_by(project_id=project_id).count() == 0


def test_contact_lead_relationship(app):
    contact = Contact(name="Jane", email="jane@example.com")
    lead = Lead(contact=contact, status="LEAD")
    db.session.add_all([contact, lead])
    db.session.commit()

    assert lead.contact.email == "jane@example.com"
    assert lead in contact.leads


def test_contact_client_relationship(app):
    contact = Contact(name="Acme", email="acme@example.com")
    client = Client(contact=contact, company="Acme Inc")
    db.session.add_all([contact, client])
    db.session.commit()

    assert client.contact.email == "acme@example.com"
    assert client in contact.clients


def test_uniqueness_constraints(app):
    first_admin = AdminUser(username="admin", email="a@example.com")
    first_admin.set_password("password")
    db.session.add(first_admin)
    db.session.add(ProjectCategory(name="Built", slug="built"))
    db.session.add(Project(title="P", slug="p"))
    db.session.commit()

    # Duplicate username.
    second_admin = AdminUser(username="admin", email="b@example.com")
    second_admin.set_password("password")
    db.session.add(second_admin)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    # Duplicate project slug.
    db.session.add(Project(title="Other", slug="p"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    # Duplicate category slug.
    db.session.add(ProjectCategory(name="Other", slug="built"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
