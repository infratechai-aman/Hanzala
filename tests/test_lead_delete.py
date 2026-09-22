"""Lead deletion tests: auth, method, CSRF, cascades, contact safety."""

from datetime import datetime, timezone

from app.models import db
from app.models.crm import Contact, Followup, Lead, Note
from tests.conftest import get_csrf_token, login, post
from tests.test_crm import make_lead


def test_unauthenticated_lead_delete_rejected(client, admin_user):
    lead = make_lead()
    token = get_csrf_token(client)  # valid token, no login
    assert client.get(f"/admin/crm/leads/{lead.id}").status_code == 302
    response = post(client, f"/admin/crm/leads/{lead.id}/delete", token)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")
    assert db.session.get(Lead, lead.id) is not None


def test_lead_delete_post_only(client, admin_user):
    lead = make_lead()
    login(client)
    assert client.get(f"/admin/crm/leads/{lead.id}/delete").status_code == 405
    assert db.session.get(Lead, lead.id) is not None


def test_lead_delete_requires_csrf(client, admin_user):
    lead = make_lead()
    login(client)
    assert client.post(f"/admin/crm/leads/{lead.id}/delete").status_code == 400
    assert db.session.get(Lead, lead.id) is not None


def test_successful_lead_deletion(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    response = post(client, f"/admin/crm/leads/{lead.id}/delete", token)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/crm/leads")
    assert db.session.get(Lead, lead.id) is None
    assert "Lead deleted." in client.get("/admin/crm/leads").get_data(as_text=True)


def test_delete_nonexistent_lead_404(client, admin_user):
    _, token = login(client)
    response = post(client, "/admin/crm/leads/9999/delete", token)
    assert response.status_code == 404


def test_delete_preserves_contact(client, admin_user):
    lead = make_lead()
    contact_id = lead.contact_id
    _, token = login(client)
    post(client, f"/admin/crm/leads/{lead.id}/delete", token)
    contact = db.session.get(Contact, contact_id)
    assert contact is not None
    assert contact.email == "jane-prospect@example.com"


def test_delete_removes_related_notes_and_followups(client, admin_user):
    lead = make_lead()
    db.session.add(Note(content="Keep?", lead_id=lead.id, contact_id=lead.contact_id))
    db.session.add(Followup(
        lead_id=lead.id,
        scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.session.commit()
    note_id = Note.query.filter_by(lead_id=lead.id).one().id
    followup_id = Followup.query.filter_by(lead_id=lead.id).one().id

    _, token = login(client)
    post(client, f"/admin/crm/leads/{lead.id}/delete", token)

    assert db.session.get(Lead, lead.id) is None
    assert db.session.get(Note, note_id) is None
    assert db.session.get(Followup, followup_id) is None
