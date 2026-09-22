"""Document vault tests: model, CRUD, auth, validation, dashboard."""

from app.models import db
from app.models.crm import Contact, Lead
from app.models.document import DOCUMENT_CATEGORIES, Document
from tests.conftest import get_csrf_token, login, post
from tests.test_crm import make_lead


def document_data(**overrides):
    data = {
        "title": "Website Development — SOW",
        "category": "CLIENT_PROJECT",
        "doc_type": "Scope of Work (SOW)",
        "description": "Scope and deliverables.",
        "status": "DRAFT",
        "url_or_path": "https://docs.example.com/sow-1",
    }
    data.update(overrides)
    return data


def make_document(**overrides):
    fields = {
        "title": "Quotation Q-1",
        "category": "PRICING_APPROVAL",
        "doc_type": "Quotation",
        "status": "DRAFT",
    }
    fields.update(overrides)
    document = Document(**fields)
    db.session.add(document)
    db.session.commit()
    return document


def test_document_model_defaults(app):
    document = Document(title="T", category="DELIVERY")
    db.session.add(document)
    db.session.commit()
    assert document.status == "DRAFT"
    assert document.category_label == "DELIVERY"
    assert document.is_legal_template is False


def test_authenticated_document_create(client, admin_user):
    _, token = login(client)
    response = post(client, "/admin/documents/new", token, document_data())
    assert response.status_code == 302
    document = Document.query.filter_by(title="Website Development — SOW").one()
    assert document.category == "CLIENT_PROJECT"
    assert document.doc_type == "Scope of Work (SOW)"
    assert document.status == "DRAFT"


def test_document_read_list_and_detail(client, admin_user):
    make_document()
    _, token = login(client)
    assert "Quotation Q-1" in client.get("/admin/documents").get_data(as_text=True)
    document = Document.query.first()
    html = client.get(f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Quotation Q-1" in html
    assert "PRICING &amp; APPROVAL" in html


def test_document_update(client, admin_user):
    document = make_document()
    _, token = login(client)
    response = post(
        client, f"/admin/documents/{document.id}/edit", token,
        document_data(title="Quotation Q-2", category="PRICING_APPROVAL",
                      doc_type="Estimate", status="READY"),
    )
    assert response.status_code == 302
    updated = db.session.get(Document, document.id)
    assert (updated.title, updated.status) == ("Quotation Q-2", "READY")


def test_document_delete(client, admin_user):
    document = make_document()
    _, token = login(client)
    assert client.get(f"/admin/documents/{document.id}/delete").status_code == 405
    response = post(client, f"/admin/documents/{document.id}/delete", token)
    assert response.status_code == 302
    assert db.session.get(Document, document.id) is None


def test_documents_require_authentication(client, admin_user):
    document = make_document()
    token = get_csrf_token(client)
    for url in ("/admin/documents", f"/admin/documents/{document.id}",
                "/admin/documents/new"):
        assert client.get(url).status_code == 302
    response = post(client, "/admin/documents/new", token, document_data())
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")
    assert Document.query.count() == 1


def test_documents_require_csrf(client, admin_user):
    make_document()
    login(client)
    assert client.post("/admin/documents/new", data=document_data()).status_code == 400


def test_document_validation(client, admin_user):
    _, token = login(client)
    # Missing title.
    response = post(client, "/admin/documents/new", token, document_data(title=""))
    assert response.status_code == 200
    # Bad category.
    response = post(client, "/admin/documents/new", token,
                    document_data(category="NOPE"))
    assert response.status_code == 200
    # Bad status.
    response = post(client, "/admin/documents/new", token,
                    document_data(status="SHIPPED"))
    assert response.status_code == 200
    # Type from the wrong category stack.
    response = post(client, "/admin/documents/new", token,
                    document_data(doc_type="Invoice / E-Bill"))
    assert response.status_code == 200
    assert Document.query.count() == 0


def test_document_category_filter(client, admin_user):
    make_document()  # PRICING_APPROVAL
    make_document(title="SOW", category="CLIENT_PROJECT",
                  doc_type="Scope of Work (SOW)")
    login(client)
    html = client.get("/admin/documents?category=DELIVERY").get_data(as_text=True)
    assert "Quotation Q-1" not in html
    assert "SOW" not in html
    html = client.get("/admin/documents?category=PRICING_APPROVAL").get_data(as_text=True)
    assert "Quotation Q-1" in html
    assert ">SOW<" not in html


def test_document_status_flow(client, admin_user):
    document = make_document()
    _, token = login(client)
    for status in ("READY", "ARCHIVED"):
        post(client, f"/admin/documents/{document.id}/edit", token,
             document_data(status=status, doc_type=""))
        assert db.session.get(Document, document.id).status == status


def test_legal_template_warning(client, admin_user):
    document = make_document(title="NDA", category="CLIENT_PROJECT",
                             doc_type="NDA — Non-Disclosure Agreement")
    login(client)
    html = client.get(f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Template — review before use." in html


def test_dashboard_documents_and_followups(client, admin_user):
    make_document(status="READY")
    make_lead(status="QUALIFIED")
    login(client)
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "dt>Total</dt><dd>1</dd>" in html
    assert "dt>Ready</dt><dd>1</dd>" in html
    assert "dt>QUALIFIED</dt><dd>1</dd>" in html
    assert "Quotation Q-1" in html
    assert "Jane Prospect" in html
    assert "Nothing requires attention." in html


def test_dashboard_followup_attention(client, admin_user):
    from datetime import datetime, timedelta, timezone

    from app.models.crm import Followup

    lead = make_lead()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.add(Followup(lead_id=lead.id,
                            scheduled_at=now - timedelta(days=1),
                            note="Overdue call"))
    db.session.add(Followup(lead_id=lead.id, scheduled_at=now + timedelta(days=3),
                            note="Later call"))
    db.session.commit()
    login(client)
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "Overdue" in html
    assert "Overdue call" in html
    assert "Upcoming" in html
    assert "Nothing requires attention." not in html


def test_seed_and_crm_data_untouched_by_documents(app):
    contact = Contact(name="Keep", email="keep2@example.com", message="Hi")
    db.session.add(contact)
    db.session.flush()
    db.session.add(Lead(contact_id=contact.id, status="LEAD"))
    db.session.commit()
    make_document()
    assert set(DOCUMENT_CATEGORIES) == {
        "CLIENT_PROJECT", "PRICING_APPROVAL", "PROJECT_EXECUTION",
        "DELIVERY", "MONEY_ACCOUNTING", "CLOSING",
    }
    assert Contact.query.count() == 1
    assert Lead.query.count() == 1
