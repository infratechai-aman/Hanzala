"""CRM tests: public contact capture, auth, leads, clients, notes, follow-ups."""

from datetime import datetime
from decimal import Decimal

from app.models import db
from app.models.crm import Client, Contact, Followup, Lead, Note
from tests.conftest import extract_csrf_token, login, post

PUBLIC_PAGES = ["/", "/work", "/context", "/learning", "/process", "/contact"]


def contact_token(client):
    return extract_csrf_token(client.get("/contact").get_data(as_text=True))


def contact_data(**overrides):
    data = {
        "name": "Prospect",
        "email": "prospect@example.com",
        "phone": "555-0100",
        "company": "Prospect Co",
        "message": "We need a small website.",
        "source": "test",
        "service_interest": "Landing page",
        "website": "",  # honeypot stays empty for humans
    }
    data.update(overrides)
    return data


def submit_contact(client, **overrides):
    return post(client, "/contact", contact_token(client), contact_data(**overrides))


def make_lead(status="LEAD", service_interest=None, estimated_value=None):
    contact = Contact(
        name="Jane Prospect",
        email="jane-prospect@example.com",
        phone="555-0101",
        company="Jane Co",
        message="Original message.",
        source="test",
    )
    db.session.add(contact)
    db.session.flush()
    lead = Lead(
        contact_id=contact.id,
        status=status,
        service_interest=service_interest,
        estimated_value=estimated_value,
    )
    db.session.add(lead)
    db.session.commit()
    return lead


# ------------------------------------------------------- public contact

def test_contact_page_loads(client):
    response = client.get("/contact")
    assert response.status_code == 200
    assert b'name="message"' in response.data
    assert b'name="website"' in response.data  # honeypot present


def test_valid_submission_creates_contact(client):
    response = submit_contact(client)
    assert response.status_code == 302
    contact = Contact.query.filter_by(email="prospect@example.com").one()
    assert contact.name == "Prospect"
    assert contact.message == "We need a small website."
    assert contact.source == "test"


def test_valid_submission_creates_lead(client):
    submit_contact(client)
    contact = Contact.query.filter_by(email="prospect@example.com").one()
    lead = Lead.query.filter_by(contact_id=contact.id).one()
    assert lead.status == "LEAD"
    assert lead.service_interest == "Landing page"


def test_lead_references_correct_contact(client):
    submit_contact(client, email="second@example.com", name="Second")
    second = Contact.query.filter_by(email="second@example.com").one()
    lead = Lead.query.filter_by(contact_id=second.id).one()
    assert lead.contact.name == "Second"


def test_invalid_email_rejected(client):
    response = submit_contact(client, email="not-an-email")
    assert response.status_code == 200
    assert b"valid email" in response.data
    assert Contact.query.count() == 0
    assert Lead.query.count() == 0


def test_missing_required_fields_rejected(client):
    response = submit_contact(client, name="", email="", message="")
    assert response.status_code == 200
    assert Contact.query.count() == 0


def test_contact_csrf_required(client):
    response = client.post("/contact", data=contact_data())
    assert response.status_code == 400
    assert Contact.query.count() == 0


def test_honeypot_submission_rejected(client):
    response = submit_contact(client, website="http://spam.example")
    # Pretends success so bots learn nothing...
    assert response.status_code == 302
    # ...but stores nothing.
    assert Contact.query.count() == 0
    assert Lead.query.count() == 0


# ------------------------------------------------------ CRM authorization

def test_unauthenticated_crm_redirects(client, admin_user):
    lead = make_lead()
    for url in ("/admin/crm", "/admin/crm/leads", "/admin/crm/contacts",
                f"/admin/crm/leads/{lead.id}"):
        response = client.get(url)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/admin/login")


def test_authenticated_crm_dashboard(client, admin_user):
    login(client)
    response = client.get("/admin/crm")
    assert response.status_code == 200
    assert b"CRM" in response.data


def test_authenticated_lead_list(client, admin_user):
    login(client)
    assert client.get("/admin/crm/leads").status_code == 200


def test_authenticated_contact_list(client, admin_user):
    login(client)
    assert client.get("/admin/crm/contacts").status_code == 200


# ----------------------------------------------------------------- leads

def test_lead_status_update(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    response = post(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "QUALIFIED", "service_interest": "", "estimated_value": "",
         "last_contacted_at": ""},
    )
    assert response.status_code == 302
    assert db.session.get(Lead, lead.id).status == "QUALIFIED"


def test_invalid_status_rejected(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    response = post(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "BOGUS", "service_interest": "", "estimated_value": "",
         "last_contacted_at": ""},
    )
    assert response.status_code == 302
    assert db.session.get(Lead, lead.id).status == "LEAD"
    assert Client.query.count() == 0


def test_service_interest_update(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    post(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "LEAD", "service_interest": "Custom web application",
         "estimated_value": "", "last_contacted_at": ""},
    )
    assert db.session.get(Lead, lead.id).service_interest == "Custom web application"


def test_estimated_value_update(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    post(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "LEAD", "service_interest": "", "estimated_value": "1500.00",
         "last_contacted_at": ""},
    )
    assert db.session.get(Lead, lead.id).estimated_value == Decimal("1500.00")


def test_last_contacted_update(client, admin_user):
    lead = make_lead()
    assert lead.last_contacted_at is None
    _, token = login(client)
    post(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "LEAD", "service_interest": "", "estimated_value": "",
         "last_contacted_at": "", "contact_now": "on"},
    )
    assert db.session.get(Lead, lead.id).last_contacted_at is not None


# ---------------------------------------------------------------- clients

def test_lead_to_client_creates_client(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    post(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "CLIENT", "service_interest": "", "estimated_value": "",
         "last_contacted_at": ""},
    )
    updated = db.session.get(Lead, lead.id)
    assert updated.status == "CLIENT"
    created = Client.query.filter_by(contact_id=lead.contact_id).one()
    assert created.company == "Jane Co"
    # Conversion, not deletion: the lead still exists.
    assert Lead.query.count() == 1


def test_repeated_conversion_no_duplicate_client(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    payload = {"status": "CLIENT", "service_interest": "", "estimated_value": "",
               "last_contacted_at": ""}
    post(client, f"/admin/crm/leads/{lead.id}/update", token, payload)
    post(client, f"/admin/crm/leads/{lead.id}/update", token, payload)
    assert Client.query.filter_by(contact_id=lead.contact_id).count() == 1


# ----------------------------------------------------------------- notes

def test_admin_can_add_note(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    response = post(
        client, f"/admin/crm/leads/{lead.id}/notes", token,
        {"content": "Called back, asked for a quote."},
    )
    assert response.status_code == 302
    note = Note.query.filter_by(lead_id=lead.id).one()
    assert note.content == "Called back, asked for a quote."
    assert note.contact_id == lead.contact_id
    assert b"Called back" in client.get(f"/admin/crm/leads/{lead.id}").data


def test_crm_notes_never_public(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    post(
        client, f"/admin/crm/leads/{lead.id}/notes", token,
        {"content": "Secret internal note 5d7f."},
    )
    for page in PUBLIC_PAGES:
        assert "Secret internal note 5d7f" not in client.get(page).get_data(as_text=True)


# ------------------------------------------------------------- follow-ups

def test_admin_can_create_followup(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    response = post(
        client, f"/admin/crm/leads/{lead.id}/followups", token,
        {"scheduled_at": "2030-01-15T10:30", "note": "Send the quote."},
    )
    assert response.status_code == 302
    followup = Followup.query.filter_by(lead_id=lead.id).one()
    assert followup.scheduled_at == datetime(2030, 1, 15, 10, 30)
    assert followup.completed_at is None


def test_admin_can_complete_followup(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    post(
        client, f"/admin/crm/leads/{lead.id}/followups", token,
        {"scheduled_at": "2030-01-15T10:30", "note": ""},
    )
    followup = Followup.query.filter_by(lead_id=lead.id).one()
    response = post(client, f"/admin/crm/followups/{followup.id}/complete", token)
    assert response.status_code == 302
    assert db.session.get(Followup, followup.id).completed_at is not None


# ---------------------------------------------------------------- privacy

def test_public_pages_contain_no_crm_data(client, admin_user):
    lead = make_lead(status="QUALIFIED", service_interest="Secret service 8a2c")
    db.session.add(Note(content="Private note 8a2c.", lead_id=lead.id,
                         contact_id=lead.contact_id))
    db.session.add(Client(contact_id=lead.contact_id, company="Secret Co 8a2c"))
    db.session.commit()
    for page in PUBLIC_PAGES:
        html = client.get(page).get_data(as_text=True)
        assert "jane-prospect@example.com" not in html
        assert "Original message." not in html
        assert "Secret service 8a2c" not in html
        assert "Private note 8a2c." not in html
        assert "Secret Co 8a2c" not in html
