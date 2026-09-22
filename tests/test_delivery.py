"""Delivery milestone tests: per-type slots, classification, variables,
OPENED recording, doc pages, dashboard rows, attachment honesty."""

from app.models import db
from app.models.crm import Followup
from app.models.document import Document
from app.models.operations import ActivityEvent
from app.services.messages import (
    build_context,
    is_sendable,
    render_message,
    sendable_marker,
)
from tests.conftest import get_csrf_token, login, post
from tests.test_actions import (
    make_lead_with_contact,
    make_ready_doc,
    prepare,
)
from tests.test_operations import authed, make_client, opost


def test_sendable_classification():
    assert is_sendable("Quotation") is True
    assert is_sendable("Proposal + Pricing Sheet") is True
    assert is_sendable("Scope of Work (SOW)") is True
    assert is_sendable("Invoice / E-Bill") is True
    assert is_sendable("Meeting Notes") is False
    assert is_sendable("Access Register") is False
    assert is_sendable("Something Unknown") is False
    assert sendable_marker("Quotation") == "Quotation"
    assert sendable_marker("Meeting Notes") is None


def test_internal_doc_never_offered(client, admin_user):
    owner = make_client()
    make_ready_doc(owner, title="Notes", doc_type="Meeting Notes",
                   number="MT-001")
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "Send</a>" not in html


def test_per_type_slots_ready_and_missing(client, admin_user):
    owner = make_client()
    make_ready_doc(owner)
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "Send Quotation" in html
    assert "QT-004" in html
    assert "Send Proposal" in html
    assert "not ready" in html


def test_draft_type_shows_not_ready(client, admin_user):
    owner = make_client()
    make_ready_doc(owner, status="DRAFT", number="QT-009")
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "Send</a>" not in html
    assert "still a draft" in html


def test_new_variables_resolve():
    ctx = build_context(client_name="Rahul", business_name="ABC Motors",
                        project_name="Site", document_number="QT-004",
                        document_url="https://files.example/q.pdf",
                        project_fee="for 50000", amount_due="Amount due: 200",
                        due_date="Due: 2030-01-01",
                        developer_name="Hanzala",
                        portfolio_url="https://portfolio.example/")
    text = render_message("QUOTATION", ctx)
    assert "QT-004" in text and "https://files.example/q.pdf" in text
    assert "for 50000" in text and "{{" not in text


def test_private_doc_url_never_leaks_into_message(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner)
    document.url_or_path = "D:\\Hanzala\\portfolio\\docs\\q.pdf"
    db.session.commit()
    _, token = login(client)
    html = client.get(
        f"/admin/crm/client/{owner.id}/actions/compose"
        f"?document_id={document.id}&purpose=QUOTATION"
    ).get_data(as_text=True)
    assert "Hanzala" not in html or "attach it manually" in html
    assert "D:\\Hanzala" not in html
    assert "Private location" in html


def test_public_doc_url_included(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner)
    document.url_or_path = "https://files.example.com/q.pdf"
    db.session.commit()
    login(client)
    html = client.get(
        f"/admin/crm/client/{owner.id}/actions/compose"
        f"?document_id={document.id}&purpose=QUOTATION"
    ).get_data(as_text=True)
    assert "https://files.example.com/q.pdf" in html


def test_compose_doc_selector_lists_ready(client, admin_user):
    owner = make_client()
    make_ready_doc(owner)
    login(client)
    html = client.get(
        f"/admin/crm/client/{owner.id}/actions/compose"
    ).get_data(as_text=True)
    assert "Attach a READY document" in html
    assert "QT-004" in html


def test_opened_recording_honest_and_idempotent(client, admin_user):
    lead = make_lead_with_contact()
    token = authed(client, admin_user)
    prepare(client, token, "lead", lead.id,
            {"purpose": "GENERAL", "channel": "WHATSAPP",
             "message": "Hello", "scheduled_at": "",
             "document_id": "", "project_id": "", "invoice_id": ""})
    followup = Followup.query.one()
    assert "OPENED" not in {e.event_type for e in ActivityEvent.query.all()}
    response = opost(client, f"/admin/actions/{followup.id}/opened", token)
    assert response.status_code == 302
    opost(client, f"/admin/actions/{followup.id}/opened", token)
    opened = ActivityEvent.query.filter_by(event_type="CHANNEL_OPENED").all()
    assert len(opened) == 1
    assert "Delivery not verified" in opened[0].description
    assert "SENT" not in {e.event_type for e in ActivityEvent.query.all()}
    html = client.get(
        f"/admin/actions/confirm/{followup.id}").get_data(as_text=True)
    assert "OPENED" in html


def test_opened_requires_auth_and_csrf(client, admin_user):
    lead = make_lead_with_contact()
    token = authed(client, admin_user)
    prepare(client, token, "lead", lead.id,
            {"purpose": "GENERAL", "channel": "EMAIL",
             "message": "Hi", "scheduled_at": "",
             "document_id": "", "project_id": "", "invoice_id": ""})
    followup = Followup.query.one()
    # Fresh anonymous session: must redirect to login, record nothing.
    post(client, "/admin/logout", token)
    anon_token = get_csrf_token(client)
    response = post(client, f"/admin/actions/{followup.id}/opened",
                    anon_token)
    assert response.status_code == 302
    assert client.post(
        f"/admin/actions/{followup.id}/opened").status_code == 400
    assert ActivityEvent.query.filter_by(
        event_type="CHANNEL_OPENED").count() == 0


def test_document_detail_send_ready(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner)
    login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Delivery context" in html
    assert "client-facing" in html
    assert "Send via" in html
    assert f"document_id={document.id}" in html
    assert "Available action" in html


def test_document_detail_draft_and_archived(client, admin_user):
    owner = make_client()
    draft = make_ready_doc(owner, status="DRAFT", number="QT-010")
    archived = make_ready_doc(owner, status="ARCHIVED", number="QT-011")
    login(client)
    html = client.get(
        f"/admin/documents/{draft.id}").get_data(as_text=True)
    assert ">Send</a>" not in html
    assert "still a draft" in html
    html = client.get(
        f"/admin/documents/{archived.id}").get_data(as_text=True)
    assert ">Send</a>" not in html
    assert "view-only" in html


def test_document_detail_internal_type(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner, title="Notes", doc_type="Meeting Notes",
                              number="MT-002")
    login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "admin-only" in html
    assert ">Send</a>" not in html


def test_document_list_send_link_scoped(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner)
    draft = make_ready_doc(owner, status="DRAFT", number="QT-012")
    login(client)
    html = client.get("/admin/documents").get_data(as_text=True)
    assert (f"document_id={document.id}" in html
            or f"/actions/compose" in html)
    # DRAFT row offers no send.
    assert html.count(">Send</a>") == 1
    assert str(draft.id) in html


def test_dashboard_rows_link_actions(client, admin_user):
    make_lead_with_contact()
    login(client)
    html = client.get("/admin/crm").get_data(as_text=True)
    assert "Client actions" in html


def test_private_paths_never_public(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner)
    document.url_or_path = "D:\\secret\\q.pdf"
    db.session.commit()
    for page in ("/", "/work", "/contact"):
        assert "secret" not in client.get(page).get_data(as_text=True)
