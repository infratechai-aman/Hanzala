"""Actionable contacts tests: list, detail, convert, status, delete."""

from app.models import db
from app.models.crm import Client, Contact, Lead, Note
from app.models.operations import ActivityEvent
from tests.conftest import get_csrf_token, login, post
from tests.test_operations import opost


def make_contact(name="Pat", phone="+91 90000 00009",
                 email="pat@example.com"):
    contact = Contact(name=name, email=email, phone=phone,
                      company="Pat Co", message="Need help.", source="web")
    db.session.add(contact)
    db.session.commit()
    return contact


def convert(client, token, contact_id, data=None):
    return opost(client, f"/admin/crm/contacts/{contact_id}/convert",
                 token, data or {})


# ------------------------------------------------------------ pages

def test_contacts_page_loads(client, admin_user):
    make_contact()
    login(client)
    html = client.get("/admin/crm/contacts").get_data(as_text=True)
    assert "Pat" in html
    assert "Convert to Lead" in html


def test_contact_detail_loads(client, admin_user):
    contact = make_contact()
    login(client)
    html = client.get(
        f"/admin/crm/contacts/{contact.id}").get_data(as_text=True)
    assert "Need help." in html
    assert "Convert to Lead" in html
    assert "tel:+91 90000 00009" in html
    assert "wa.me/919000000009" in html
    assert "mailto:pat@example.com" in html


def test_unauthenticated_contacts_blocked(client, admin_user):
    contact = make_contact()
    for url in ("/admin/crm/contacts",
                f"/admin/crm/contacts/{contact.id}",
                f"/admin/crm/contacts/{contact.id}/convert"):
        assert client.get(url).status_code == 302


# --------------------------------------------------------- conversion

def test_convert_requires_auth(client, admin_user):
    contact = make_contact()
    token = get_csrf_token(client)
    response = post(
        client, f"/admin/crm/contacts/{contact.id}/convert", token,
        {"service_interest": "Site"})
    assert response.status_code == 302
    assert Lead.query.count() == 0


def test_convert_requires_csrf(client, admin_user):
    contact = make_contact()
    login(client)
    response = client.post(
        f"/admin/crm/contacts/{contact.id}/convert",
        data={"service_interest": "Site"})
    assert response.status_code == 400
    assert Lead.query.count() == 0


def test_convert_creates_exactly_one_lead(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    response = convert(client, token, contact.id,
                       {"service_interest": "Site", "estimated_value": "",
                        "note": "Hot inquiry."})
    assert response.status_code == 302
    leads = Lead.query.filter_by(contact_id=contact.id).all()
    assert len(leads) == 1
    assert leads[0].status == "LEAD"
    assert leads[0].service_interest == "Site"
    assert f"/admin/crm/leads/{leads[0].id}" in response.headers["Location"]
    note = Note.query.filter_by(lead_id=leads[0].id).one()
    assert note.content == "Hot inquiry."


def test_repeated_convert_no_duplicate(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {"service_interest": "Site"})
    convert(client, token, contact.id, {"service_interest": "Site"})
    assert Lead.query.filter_by(contact_id=contact.id).count() == 1


def test_contact_preserved_and_linked(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {})
    assert db.session.get(Contact, contact.id) is not None
    html = client.get(
        f"/admin/crm/contacts/{contact.id}").get_data(as_text=True)
    assert "View Lead" in html
    assert "Convert to Lead" not in html


def test_convert_review_shows_contact_data(client, admin_user):
    contact = make_contact()
    login(client)
    html = client.get(
        f"/admin/crm/contacts/{contact.id}/convert").get_data(as_text=True)
    assert "Need help." in html
    assert "Pat Co" in html


# ------------------------------------------------------------- status

def test_lead_status_change_from_contact(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {})
    lead = Lead.query.filter_by(contact_id=contact.id).one()
    response = opost(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "QUALIFIED", "service_interest": "",
         "estimated_value": "", "last_contacted_at": "",
         "next": f"/admin/crm/contacts/{contact.id}"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/admin/crm/contacts/{contact.id}")
    assert db.session.get(Lead, lead.id).status == "QUALIFIED"


def test_invalid_status_rejected(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {})
    lead = Lead.query.filter_by(contact_id=contact.id).one()
    opost(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "BOGUS", "service_interest": "",
         "estimated_value": "", "last_contacted_at": ""})
    assert db.session.get(Lead, lead.id).status == "LEAD"


def test_unsafe_next_redirect_rejected(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {})
    lead = Lead.query.filter_by(contact_id=contact.id).one()
    response = opost(
        client, f"/admin/crm/leads/{lead.id}/update", token,
        {"status": "QUALIFIED", "service_interest": "",
         "estimated_value": "", "last_contacted_at": "",
         "next": "https://evil.example/"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/admin/crm/leads/{lead.id}")


def test_lead_to_client_flow_and_idempotency(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {})
    lead = Lead.query.filter_by(contact_id=contact.id).one()
    payload = {"status": "CLIENT", "service_interest": "",
               "estimated_value": "", "last_contacted_at": ""}
    opost(client, f"/admin/crm/leads/{lead.id}/update", token, payload)
    opost(client, f"/admin/crm/leads/{lead.id}/update", token, payload)
    assert Client.query.filter_by(contact_id=contact.id).count() == 1
    assert Lead.query.filter_by(contact_id=contact.id).count() == 1
    html = client.get(
        f"/admin/crm/contacts/{contact.id}").get_data(as_text=True)
    assert "View Client" in html


# ------------------------------------------------------------- delete

def test_contact_delete_requires_post(client, admin_user):
    contact = make_contact()
    login(client)
    assert client.get(
        f"/admin/crm/contacts/{contact.id}/delete").status_code == 405
    assert db.session.get(Contact, contact.id) is not None


def test_contact_delete_requires_csrf(client, admin_user):
    contact = make_contact()
    login(client)
    assert client.post(
        f"/admin/crm/contacts/{contact.id}/delete").status_code == 400
    assert db.session.get(Contact, contact.id) is not None


def test_contact_delete_blocked_with_history(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    convert(client, token, contact.id, {})
    response = opost(
        client, f"/admin/crm/contacts/{contact.id}/delete", token)
    assert response.status_code == 302
    assert db.session.get(Contact, contact.id) is not None
    assert Lead.query.filter_by(contact_id=contact.id).count() == 1


def test_bare_contact_deletes_cleanly(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    response = opost(
        client, f"/admin/crm/contacts/{contact.id}/delete", token)
    assert response.status_code == 302
    assert db.session.get(Contact, contact.id) is None


# --------------------------------------------------- actions honesty

def test_call_whatsapp_email_use_stored_data(client, admin_user):
    contact = make_contact()
    login(client)
    html = client.get("/admin/crm/contacts").get_data(as_text=True)
    assert "tel:+91 90000 00009" in html
    assert "wa.me/919000000009" in html
    assert "mailto:pat@example.com" in html
    assert "MESSAGE SENT" not in html
    assert "Message sent" not in html


def test_contact_without_phone_shows_no_call(client, admin_user):
    make_contact(name="Nophone", phone=None, email="nophone@example.com")
    login(client)
    html = client.get("/admin/crm/contacts").get_data(as_text=True)
    assert "tel:" not in html


def test_filter_states(client, admin_user):
    make_contact(name="Nina", email="nina@example.com", phone=None)
    converted = make_contact(name="Omar", email="omar@example.com", phone=None)
    _, token = login(client)
    convert(client, token, converted.id, {})
    html_all = client.get("/admin/crm/contacts").get_data(as_text=True)
    assert "Nina" in html_all and "Omar" in html_all
    html_new = client.get(
        "/admin/crm/contacts?state=NEW").get_data(as_text=True)
    assert "Nina" in html_new
    assert "Omar" not in html_new
    html_lead = client.get(
        "/admin/crm/contacts?state=LEAD").get_data(as_text=True)
    assert "Omar" in html_lead
    assert "Nina" not in html_lead
    assert Contact.query.count() == 2  # filtering never destroys records


def test_dashboard_counts_consistent(client, admin_user):
    contact = make_contact()
    _, token = login(client)
    before_leads = Lead.query.count()
    before_clients = Client.query.count()
    convert(client, token, contact.id, {})
    assert Lead.query.count() == before_leads + 1
    assert Contact.query.count() >= 1
    lead = Lead.query.filter_by(contact_id=contact.id).one()
    opost(client, f"/admin/crm/leads/{lead.id}/update", token,
          {"status": "CLIENT", "service_interest": "",
           "estimated_value": "", "last_contacted_at": ""})
    assert Client.query.count() == before_clients + 1
    assert db.session.get(Contact, contact.id) is not None
    assert "LEAD_CREATED" in {e.event_type for e in ActivityEvent.query.all()}
