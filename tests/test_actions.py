"""Action Center tests: contact actions, document sending rules,
follow-up composer, templates, logging honesty, and scoping."""

from app.models import db
from app.models.crm import Client, Contact, Followup, Lead
from app.models.document import Document
from app.models.operations import ActivityEvent, DocumentVersion
from app.services.messages import (
    mailto_url,
    render_message,
    sms_url,
    whatsapp_url,
)
from tests.conftest import get_csrf_token, login, post
from tests.test_crm import make_lead
from tests.test_operations import authed, make_client, make_project, opost


def make_contact(name="Zed", phone=None, email="zed@example.com"):
    contact = Contact(name=name, email=email, phone=phone,
                      company="Zed Co", message="Hi")
    db.session.add(contact)
    db.session.flush()
    return contact


def make_lead_with_contact(phone="+91 90000 00001"):
    contact = make_contact(phone=phone)
    lead = Lead(contact_id=contact.id, status="QUALIFIED",
                service_interest="Website")
    db.session.add(lead)
    db.session.commit()
    return lead


def make_ready_doc(client, title="Quote", doc_type="Quotation",
                   status="READY", number="QT-004"):
    document = Document(
        title=title, category="PRICING_APPROVAL", doc_type=doc_type,
        status=status, client_id=client.id, document_number=number,
    )
    db.session.add(document)
    db.session.flush()
    db.session.add(DocumentVersion(
        document_id=document.id, version_number=1, title=title,
        status="DRAFT"))
    db.session.flush()
    document.current_version_id = document.versions[0].id
    db.session.commit()
    return document


def prepare(client, token, scope, scope_id, data):
    return opost(client, f"/admin/crm/{scope}/{scope_id}/actions/prepare",
                 token, data)


# ------------------------------------------------------- contact actions

def test_call_action_uses_stored_phone(client, admin_user):
    lead = make_lead_with_contact(phone="+91 90000 00001")
    login(client)
    html = client.get(f"/admin/crm/leads/{lead.id}").get_data(as_text=True)
    assert "Action center" in html
    assert 'href="tel:+91 90000 00001"' in html


def test_missing_phone_hides_phone_actions(client, admin_user):
    owner = make_client()  # contact has no phone
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "tel:" not in html
    assert "no phone number recorded" in html


def test_missing_email_hides_email_action(client, admin_user):
    # Contact.email is non-nullable in the schema, so exercise the
    # helper directly with an email-less record.
    from types import SimpleNamespace

    from app.routes.admin.actions import contact_action_links

    links = contact_action_links(
        SimpleNamespace(phone="+91 90000 00002", email=""))
    assert links["has_email"] is False
    assert links["has_whatsapp"] is True
    links = contact_action_links(
        SimpleNamespace(phone="", email="zed@example.com"))
    assert links["has_whatsapp"] is False
    assert links["tel"] is None


def test_email_action_uses_stored_address(client, admin_user):
    lead = make_lead_with_contact()
    login(client)
    html = client.get(f"/admin/crm/leads/{lead.id}").get_data(as_text=True)
    assert "Email" in html
    assert "zed@example.com" in html


def test_no_cross_client_contact_leak(client, admin_user):
    first = make_lead_with_contact(phone="+91 91111 11111")
    make_lead_with_contact(phone="+91 92222 22222")
    login(client)
    html = client.get(f"/admin/crm/leads/{first.id}").get_data(as_text=True)
    assert "+91 91111 11111" in html
    assert "+91 92222 22222" not in html


# ----------------------------------------------------- document actions

def test_ready_document_can_be_prepared(client, admin_user):
    owner = make_client()
    make_ready_doc(owner)
    token = authed(client, admin_user)
    response = prepare(
        client, token, "client", owner.id,
        {"purpose": "QUOTATION", "channel": "EMAIL",
         "message": "Please review the quotation.", "scheduled_at": "",
         "document_id": str(
             Document.query.filter_by(client_id=owner.id).one().id),
         "project_id": "", "invoice_id": ""},
    )
    assert response.status_code == 302
    followup = Followup.query.filter_by(
        document_id=Document.query.filter_by(client_id=owner.id).one().id,
    ).one()
    assert followup.purpose == "QUOTATION"
    assert followup.channel == "EMAIL"
    assert followup.message == "Please review the quotation."
    assert "DOCUMENT_PREPARED" in {
        e.event_type for e in ActivityEvent.query.all()}


def test_draft_document_cannot_be_sent_as_ready(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner, status="DRAFT", number="QT-005")
    token = authed(client, admin_user)
    response = prepare(
        client, token, "client", owner.id,
        {"purpose": "QUOTATION", "channel": "EMAIL",
         "message": "Trying to send a draft.", "scheduled_at": "",
         "document_id": str(document.id), "project_id": "", "invoice_id": ""},
    )
    assert response.status_code == 200  # recomposed with error, not stored
    assert Followup.query.count() == 0
    assert "Only READY documents" in response.get_data(as_text=True)


def test_archived_document_treated_as_view_only(client, admin_user):
    owner = make_client()
    make_ready_doc(owner, status="ARCHIVED", number="QT-006")
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "No ready documents" in html
    assert "archived documents are view-only" in html


def test_private_document_access_protected(client, admin_user):
    owner = make_client()
    other = make_client("Other")
    document = make_ready_doc(other, number="QT-007")
    token = authed(client, admin_user)
    # Forge owner's scope with the other client's document id.
    response = prepare(
        client, token, "client", owner.id,
        {"purpose": "QUOTATION", "channel": "EMAIL",
         "message": "Cross-client forgery.", "scheduled_at": "",
         "document_id": str(document.id), "project_id": "", "invoice_id": ""},
    )
    assert response.status_code == 302
    # Scoping drops the foreign document: no document link stored.
    stored = Followup.query.one()
    assert stored.document_id is None
    assert stored.message == "Cross-client forgery."


def test_compose_unknown_scope_404(client, admin_user):
    login(client)
    assert client.get("/admin/crm/nonsense/1/actions/compose").status_code == 404


# ---------------------------------------------------------- follow-ups

def test_followup_purpose_channel_message_saved(client, admin_user):
    lead = make_lead_with_contact()
    token = authed(client, admin_user)
    response = prepare(
        client, token, "lead", lead.id,
        {"purpose": "MEETING", "channel": "WHATSAPP",
         "message": "Confirming Tuesday 10am.",
         "scheduled_at": "2030-05-01T10:00",
         "document_id": "", "project_id": "", "invoice_id": ""},
    )
    assert response.status_code == 302
    followup = Followup.query.filter_by(lead_id=lead.id).one()
    assert followup.purpose == "MEETING"
    assert followup.channel == "WHATSAPP"
    assert followup.message == "Confirming Tuesday 10am."


def test_followup_invalid_purpose_rejected(client, admin_user):
    lead = make_lead_with_contact()
    token = authed(client, admin_user)
    response = prepare(
        client, token, "lead", lead.id,
        {"purpose": "BOGUS", "channel": "EMAIL", "message": "Hi",
         "scheduled_at": "", "document_id": "", "project_id": "",
         "invoice_id": ""},
    )
    assert response.status_code == 200
    assert Followup.query.count() == 0


def test_followup_channel_needs_contact_method(client, admin_user):
    owner = make_client()  # no phone on file
    lead = owner.contact.leads[0]
    token = authed(client, admin_user)
    response = prepare(
        client, token, "lead", lead.id,
        {"purpose": "GENERAL", "channel": "WHATSAPP", "message": "Hi",
         "scheduled_at": "", "document_id": "", "project_id": "",
         "invoice_id": ""},
    )
    assert response.status_code == 200
    assert "needs a phone number" in response.get_data(as_text=True)
    assert Followup.query.count() == 0


def test_compose_prefills_template_message(client, admin_user):
    lead = make_lead_with_contact()
    login(client)
    html = client.get(
        f"/admin/crm/lead/{lead.id}/actions/compose?purpose=PROPOSAL"
    ).get_data(as_text=True)
    assert "Zed" in html
    assert "following up regarding the proposal" in html
    assert "RECIPIENT" in html or "Recipient" in html


def test_confirm_page_shows_channel_link_without_claiming_sent(
        client, admin_user):
    lead = make_lead_with_contact()
    token = authed(client, admin_user)
    prepare(
        client, token, "lead", lead.id,
        {"purpose": "GENERAL", "channel": "WHATSAPP", "message": "Hello Zed",
         "scheduled_at": "", "document_id": "", "project_id": "",
         "invoice_id": ""},
    )
    followup = Followup.query.one()
    html = client.get(
        f"/admin/actions/confirm/{followup.id}").get_data(as_text=True)
    assert "Message prepared" in html
    assert "not sent" in html
    assert "wa.me/919000000001" in html
    assert "Hello%20Zed" in html
    assert "MESSAGE SENT" not in html
    assert "cannot be verified" in html.lower()  # honesty notice present


def test_action_does_not_falsely_record_sent(client, admin_user):
    lead = make_lead_with_contact()
    token = authed(client, admin_user)
    prepare(
        client, token, "lead", lead.id,
        {"purpose": "GENERAL", "channel": "EMAIL", "message": "Hi Zed",
         "scheduled_at": "", "document_id": "", "project_id": "",
         "invoice_id": ""},
    )
    types = {e.event_type for e in ActivityEvent.query.all()}
    assert "FOLLOW_UP_PREPARED" in types
    assert "EMAIL_PREPARED" in types
    assert not {t for t in types if "SENT" in t or "DELIVERED" in t}


def test_suggestions_reflect_real_state(client, admin_user):
    owner = make_client()
    make_ready_doc(owner)
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "Suggested next actions" in html
    assert "QT-004" in html
    assert "is READY" in html


# ------------------------------------------------------------ templates

def test_template_variables_substituted():
    from app.services.messages import build_context

    ctx = build_context(client_name="Rahul", project_name="Website")
    text = render_message("QUOTATION", ctx)
    assert "Rahul" in text
    assert "Website" in text
    assert "{{" not in text


def test_undefined_variables_handled_safely():
    text = render_message("QUOTATION", {})
    assert "{{" not in text
    assert "}}" not in text
    assert "prepared the quotation" in text


def test_unknown_template_renders_empty():
    assert render_message("NONSENSE", {"client_name": "X"}) == ""


def test_channel_links_formed_correctly():
    wa = whatsapp_url("+91 90000 00001", "Hello Zed")
    assert wa.startswith("https://wa.me/919000000001?text=")
    assert "Hello%20Zed" in wa
    sms = sms_url("+91 90000 00001", "Hi")
    assert sms.startswith("sms:")
    mail = mailto_url("zed@example.com", "Quote", "Hi Zed")
    assert mail.startswith("mailto:zed@example.com?")
    assert "subject=Quote" in mail


# ------------------------------------------------------------ security

def test_prepare_requires_auth(client, admin_user):
    lead = make_lead_with_contact()
    token = get_csrf_token(client)
    response = post(
        client, f"/admin/crm/lead/{lead.id}/actions/prepare", token,
        {"purpose": "GENERAL", "channel": "EMAIL", "message": "Hi"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")
    assert Followup.query.count() == 0


def test_prepare_requires_csrf(client, admin_user):
    lead = make_lead_with_contact()
    login(client)
    response = client.post(
        f"/admin/crm/lead/{lead.id}/actions/prepare",
        data={"purpose": "GENERAL", "channel": "EMAIL", "message": "Hi"},
    )
    assert response.status_code == 400
    assert Followup.query.count() == 0


def test_compose_requires_auth(client, admin_user):
    lead = make_lead_with_contact()
    response = client.get(f"/admin/crm/lead/{lead.id}/actions/compose")
    assert response.status_code == 302


def test_existing_crm_intact(client, admin_user):
    lead = make_lead()
    _, token = login(client)
    response = post(
        client, f"/admin/crm/leads/{lead.id}/notes", token,
        {"content": "Still works."},
    )
    assert response.status_code == 302
    assert "Action center" in client.get(
        f"/admin/crm/leads/{lead.id}").get_data(as_text=True)
