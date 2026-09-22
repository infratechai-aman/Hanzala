"""Client operations tests: versioning, approvals, audit trail,
execution records, acceptance, finance, auth, and hub integration."""

from datetime import date
from decimal import Decimal

import pytest

from app.models import db
from app.models.crm import Client, Contact, Lead
from app.models.document import Document
from app.models.operations import (
    Acceptance,
    ActivityEvent,
    Approval,
    ClientProject,
    Deliverable,
    DocumentVersion,
    Invoice,
    Milestone,
    Payment,
    RevisionRequest,
)
from tests.conftest import get_csrf_token, login, post
from tests.test_crm import make_lead


def make_client(contact_name="Acme"):
    contact = Contact(
        name=f"{contact_name} Owner",
        email=f"{contact_name.lower().replace(' ', '')}@example.com",
        company=f"{contact_name} Co",
        message="Need a system.",
    )
    db.session.add(contact)
    db.session.flush()
    db.session.add(Lead(contact_id=contact.id, status="LEAD"))
    client = Client(contact_id=contact.id, company=f"{contact_name} Co")
    db.session.add(client)
    db.session.commit()
    return client


def make_project(client, name="Website", status="ACTIVE"):
    project = ClientProject(client_id=client.id, name=name, status=status)
    db.session.add(project)
    db.session.commit()
    return project


def authed(client, admin_user):
    _, token = login(client)
    return token


def opost(client, url, token, data=None):
    """POST then expire the test session's identity map.

    The test client runs requests in their own session while the `app`
    fixture session keeps cached objects; without expiring, assertions
    on rows loaded before the POST would see stale attribute state.
    """
    response = post(client, url, token, data)
    db.session.expire_all()
    return response


# ------------------------------------------------- client hub

def test_client_hub_loads_with_sections(client, admin_user):
    owner = make_client()
    make_project(owner)
    login(client)
    html = client.get(f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    for section in ("Communication", "Projects", "Commercial records",
                    "Finance", "Notes", "Activity timeline"):
        assert section in html
    assert "Acme Owner" in html


def test_client_hub_requires_auth(client, admin_user):
    owner = make_client()
    response = client.get(f"/admin/crm/clients/{owner.id}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")


def test_contact_page_links_client_hub(client, admin_user):
    owner = make_client()
    login(client)
    html = client.get(
        f"/admin/crm/contacts/{owner.contact_id}").get_data(as_text=True)
    assert f"/admin/crm/clients/{owner.id}" in html


# ----------------------------------------------- document versions

def test_commercial_document_creates_version(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    response = opost(
        client, f"/admin/crm/clients/{owner.id}/documents", token,
        {"kind": "QUOTATION", "title": "Quote for Acme", "description": "",
         "project_id": ""},
    )
    assert response.status_code == 302
    document = Document.query.filter_by(client_id=owner.id).one()
    assert document.document_number.startswith("QT-")
    versions = DocumentVersion.query.filter_by(
        document_id=document.id).all()
    assert len(versions) == 1
    assert versions[0].version_number == 1
    assert document.current_version_id == versions[0].id
    assert ActivityEvent.query.filter_by(event_type="DOCUMENT_CREATED").count() == 1


def test_new_version_preserves_history(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/documents", token,
        {"kind": "SOW", "title": "SOW v1 title", "description": "orig",
         "project_id": ""},
    )
    document = Document.query.filter_by(client_id=owner.id).one()
    opost(
        client, f"/admin/documents/{document.id}/versions", token,
        {"title": "SOW v2 title", "description": "revised", "url_or_path": ""},
    )
    versions = DocumentVersion.query.filter_by(
        document_id=document.id).order_by(DocumentVersion.version_number).all()
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[0].title == "SOW v1 title"  # history preserved
    assert versions[0].status == "SUPERSEDED"
    assert versions[1].title == "SOW v2 title"
    assert document.current_version_id == versions[1].id


def test_legacy_document_edit_preserves_version(client, admin_user):
    document = Document(title="Old", category="DELIVERY", status="DRAFT")
    db.session.add(document)
    db.session.commit()
    token = authed(client, admin_user)
    from tests.test_documents import document_data

    opost(
        client, f"/admin/documents/{document.id}/edit", token,
        document_data(title="New", category="DELIVERY", doc_type="",
                      status="READY"),
    )
    versions = DocumentVersion.query.filter_by(document_id=document.id).all()
    assert len(versions) >= 1  # history kept, never silently overwritten
    assert db.session.get(Document, document.id).title == "New"


# ------------------------------------------------------ approvals

def test_approval_references_exact_version(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/documents", token,
        {"kind": "PROPOSAL", "title": "Prop", "description": "",
         "project_id": ""},
    )
    document = Document.query.filter_by(client_id=owner.id).one()
    v1 = DocumentVersion.query.filter_by(document_id=document.id).one()
    opost(
        client, f"/admin/documents/versions/{v1.id}/approvals", token,
        {"approval_type": "DOCUMENT_APPROVAL", "status": "APPROVED",
         "approver_name": "Acme Owner", "notes": ""},
    )
    # New version afterwards: approval must NOT transfer.
    opost(
        client, f"/admin/documents/{document.id}/versions", token,
        {"title": "Prop", "description": "changed", "url_or_path": ""},
    )
    versions = DocumentVersion.query.filter_by(
        document_id=document.id).order_by(DocumentVersion.version_number).all()
    assert db.session.get(DocumentVersion, v1.id).status == "APPROVED"
    assert versions[1].status == "DRAFT"
    assert versions[1].approvals == []
    approval = Approval.query.one()
    assert approval.document_version_id == v1.id


def test_approval_status_changes(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/documents", token,
        {"kind": "QUOTATION", "title": "Q", "description": "",
         "project_id": ""},
    )
    document = Document.query.filter_by(client_id=owner.id).one()
    v1 = DocumentVersion.query.filter_by(document_id=document.id).one()
    opost(
        client, f"/admin/documents/versions/{v1.id}/approvals", token,
        {"approval_type": "SCOPE_APPROVAL", "status": "PENDING",
         "approver_name": "", "notes": ""},
    )
    approval = Approval.query.one()
    opost(client, f"/admin/approvals/{approval.id}/status", token,
         {"status": "REJECTED"})
    assert db.session.get(Approval, approval.id).status == "REJECTED"
    assert db.session.get(DocumentVersion, v1.id).status == "REJECTED"
    assert ActivityEvent.query.filter_by(
        event_type="DOCUMENT_REJECTED").count() == 1


def test_pending_approvals_on_dashboard(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/documents", token,
        {"kind": "QUOTATION", "title": "Q", "description": "",
         "project_id": ""},
    )
    document = Document.query.filter_by(client_id=owner.id).one()
    v1 = DocumentVersion.query.filter_by(document_id=document.id).one()
    opost(
        client, f"/admin/documents/versions/{v1.id}/approvals", token,
        {"approval_type": "DOCUMENT_APPROVAL", "status": "PENDING",
         "approver_name": "", "notes": ""},
    )
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "Pending Approvals" in html
    assert "dt>Pending Approvals</dt><dd>1</dd>" in html


# ---------------------------------------------------- audit trail

def test_audit_chronology_on_hub(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/ops/projects/{project.id}/milestones", token,
        {"name": "Design", "description": "", "due_date": ""},
    )
    milestone = Milestone.query.filter_by(project_id=project.id).one()
    opost(client, f"/admin/ops/milestones/{milestone.id}/update", token,
         {"status": "COMPLETED", "due_date": ""})
    opost(
        client, f"/admin/crm/clients/{owner.id}/invoices", token,
        {"amount": "500.00", "project_id": str(project.id), "due_at": ""},
    )
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    created_pos = html.find("MILESTONE_CREATED")
    completed_pos = html.find("MILESTONE_COMPLETED")
    invoice_pos = html.find("INVOICE_CREATED")
    assert created_pos != -1 and completed_pos != -1 and invoice_pos != -1
    assert created_pos < completed_pos < invoice_pos
    assert "not legal proof" in html


def test_activity_has_no_edit_or_delete_routes(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    opost(client, f"/admin/crm/clients/{owner.id}/notes", token,
         {"content": "hello"})
    event = ActivityEvent.query.one()
    assert client.get(
        f"/admin/activity/{event.id}/edit").status_code == 404
    assert client.post(
        f"/admin/activity/{event.id}/delete").status_code in (404, 405)


def test_crm_mutations_log_events(client, admin_user):
    lead = make_lead()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/leads/{lead.id}/notes", token,
        {"content": "Called back."},
    )
    opost(
        client, f"/admin/crm/leads/{lead.id}/followups", token,
        {"scheduled_at": "2030-01-15T10:30", "note": ""},
    )
    types = {e.event_type for e in ActivityEvent.query.all()}
    assert "NOTE_ADDED" in types
    assert "FOLLOWUP_SCHEDULED" in types


# ------------------------------------------------------ execution

def test_milestone_crud(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/ops/projects/{project.id}/milestones", token,
        {"name": "Design", "description": "UI", "due_date": "2030-02-01"},
    )
    milestone = Milestone.query.filter_by(project_id=project.id).one()
    assert milestone.status == "PLANNED"
    assert milestone.due_date == date(2030, 2, 1)
    opost(client, f"/admin/ops/milestones/{milestone.id}/update", token,
         {"status": "IN_PROGRESS", "due_date": ""})
    assert db.session.get(Milestone, milestone.id).status == "IN_PROGRESS"
    opost(client, f"/admin/ops/milestones/{milestone.id}/update", token,
         {"status": "COMPLETED", "due_date": ""})
    done = db.session.get(Milestone, milestone.id)
    assert done.status == "COMPLETED"
    assert done.completed_at is not None


def test_deliverable_crud(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/ops/projects/{project.id}/deliverables", token,
        {"name": "Homepage", "description": ""},
    )
    deliverable = Deliverable.query.filter_by(project_id=project.id).one()
    opost(client, f"/admin/ops/deliverables/{deliverable.id}/update", token,
         {"status": "DELIVERED"})
    assert db.session.get(Deliverable, deliverable.id).status == "DELIVERED"
    opost(client, f"/admin/ops/deliverables/{deliverable.id}/update", token,
         {"status": "ACCEPTED"})
    accepted = db.session.get(Deliverable, deliverable.id)
    assert accepted.status == "ACCEPTED"
    assert accepted.accepted_at is not None


def test_revision_crud(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/ops/projects/{project.id}/revisions", token,
        {"description": "Change hero copy."},
    )
    revision = RevisionRequest.query.filter_by(project_id=project.id).one()
    assert revision.status == "OPEN"
    opost(client, f"/admin/ops/revisions/{revision.id}/update", token,
         {"status": "COMPLETED"})
    done = db.session.get(RevisionRequest, revision.id)
    assert done.status == "COMPLETED"
    assert done.completed_at is not None


def test_acceptance_flow(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/ops/projects/{project.id}/acceptances", token,
        {"acceptance_type": "FINAL_SIGN_OFF", "deliverable_id": "",
         "client_name": "Acme Owner", "notes": "Looks good."},
    )
    acceptance = Acceptance.query.filter_by(project_id=project.id).one()
    assert acceptance.status == "PENDING"
    opost(client, f"/admin/ops/acceptances/{acceptance.id}/update", token,
         {"status": "ACCEPTED"})
    done = db.session.get(Acceptance, acceptance.id)
    assert done.status == "ACCEPTED"
    assert done.accepted_at is not None
    assert ActivityEvent.query.filter_by(
        event_type="CLIENT_ACCEPTED").count() >= 1


# -------------------------------------------------------- finance

def test_invoice_payment_and_outstanding(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/invoices", token,
        {"amount": "1000.00", "project_id": str(project.id), "due_at": ""},
    )
    invoice = Invoice.query.filter_by(client_id=owner.id).one()
    assert invoice.invoice_number.startswith("INV-")
    assert invoice.amount == Decimal("1000.00")
    assert invoice.outstanding == Decimal("1000.00")
    opost(client, f"/admin/ops/invoices/{invoice.id}/payments", token,
         {"amount": "400.00", "reference": "TRX-1", "notes": ""})
    invoice = db.session.get(Invoice, invoice.id)
    assert invoice.amount_paid == Decimal("400.00")
    assert invoice.outstanding == Decimal("600.00")
    assert invoice.status == "PARTIALLY_PAID"
    opost(client, f"/admin/ops/invoices/{invoice.id}/payments", token,
         {"amount": "600.00", "reference": "TRX-2", "notes": ""})
    invoice = db.session.get(Invoice, invoice.id)
    assert invoice.status == "PAID"
    assert invoice.outstanding == Decimal("0.00")
    assert invoice.paid_at is not None


def test_unpaid_invoice_metric(client, admin_user):
    owner = make_client()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/invoices", token,
        {"amount": "200.00", "project_id": "", "due_at": ""},
    )
    invoice = Invoice.query.one()
    opost(client, f"/admin/ops/invoices/{invoice.id}/status", token,
         {"status": "ISSUED"})
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "dt>Unpaid Invoices</dt><dd>1</dd>" in html


# -------------------------------------------------- relationships

def test_client_project_relationships(client, admin_user):
    owner = make_client()
    project = make_project(owner, name="Portal")
    assert project.client_id == owner.id
    assert owner.projects[0].name == "Portal"
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/clients/{owner.id}/invoices", token,
        {"amount": "50.00", "project_id": str(project.id), "due_at": ""},
    )
    invoice = Invoice.query.one()
    assert invoice.project_id == project.id
    assert invoice.client_id == owner.id


# ------------------------------------------------------- security

def test_operations_require_auth(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = get_csrf_token(client)
    response = opost(
        client, f"/admin/ops/projects/{project.id}/milestones", token,
        {"name": "X", "description": "", "due_date": ""},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")
    assert Milestone.query.count() == 0


def test_operations_require_csrf(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    login(client)
    response = client.post(
        f"/admin/ops/projects/{project.id}/milestones",
        data={"name": "X", "description": "", "due_date": ""},
    )
    assert response.status_code == 400
    assert Milestone.query.count() == 0


def test_private_ops_data_never_public(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(
        client, f"/admin/ops/projects/{project.id}/milestones", token,
        {"name": "Secret milestone 9z1q", "description": "", "due_date": ""},
    )
    for page in ("/", "/work", "/context", "/learning", "/process",
                 "/contact"):
        assert "Secret milestone 9z1q" not in client.get(
            page).get_data(as_text=True)


def test_invalid_statuses_rejected(client, admin_user):
    owner = make_client()
    project = make_project(owner)
    token = authed(client, admin_user)
    opost(client, f"/admin/ops/projects/{project.id}/milestones", token,
         {"name": "M", "description": "", "due_date": ""})
    milestone = Milestone.query.one()
    opost(client, f"/admin/ops/milestones/{milestone.id}/update", token,
         {"status": "BOGUS", "due_date": ""})
    assert db.session.get(Milestone, milestone.id).status == "PLANNED"


def test_media_allows_verified_remote_urls(app):
    from app.routes.admin.projects import is_safe_file_path

    assert is_safe_file_path(
        "https://umama-motors.onrender.com/static/logo.svg") is True
    assert is_safe_file_path("../../../etc/passwd") is False
    assert is_safe_file_path("/absolute/path.png") is False
    assert is_safe_file_path("javascript:alert(1)") is False
