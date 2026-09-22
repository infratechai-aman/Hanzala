"""Operations dashboard tests: ledger structure, real-data visuals,
intentional empty states, and preserved admin chrome."""

from decimal import Decimal

from app.models import db
from app.models.operations import ActivityEvent
from tests.conftest import login
from tests.test_operations import make_client, make_project, opost


def dashboard_html(client, admin_user):
    login(client)
    return client.get("/admin/dashboard").get_data(as_text=True)


def test_masthead_and_record_language(client, admin_user):
    html = dashboard_html(client, admin_user)
    assert "Operations" in html
    assert "Private Admin" in html
    assert "Last updated" in html
    for heading in ("Overview", "Attention", "Lead pipeline",
                    "Project operations", "Documents", "Finance",
                    "Activity", "Commands"):
        assert heading in html


def test_metrics_reflect_real_records(client, admin_user):
    owner = make_client()
    make_project(owner, status="ACTIVE")
    token = login(client)[1]
    opost(
        client, f"/admin/crm/clients/{owner.id}/documents", token,
        {"kind": "QUOTATION", "title": "Q", "description": "",
         "project_id": ""},
    )
    from app.models.document import Document
    from app.models.operations import DocumentVersion

    document = Document.query.filter_by(client_id=owner.id).one()
    version = DocumentVersion.query.filter_by(
        document_id=document.id).one()
    opost(
        client, f"/admin/documents/versions/{version.id}/approvals", token,
        {"approval_type": "DOCUMENT_APPROVAL", "status": "PENDING",
         "approver_name": "", "notes": ""},
    )
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "dt>Active Clients</dt><dd>1</dd>" in html
    assert "dt>Active Projects</dt><dd>1</dd>" in html
    assert "dt>Pending Approvals</dt><dd>1</dd>" in html


def test_activity_chart_uses_real_events(client, admin_user):
    owner = make_client()
    token = login(client)[1]
    opost(client, f"/admin/crm/clients/{owner.id}/notes", token,
          {"content": "chart check"})
    assert ActivityEvent.query.count() >= 1
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "<svg" in html
    assert "NOTE_ADDED" in html
    assert "Chronological application activity record" in html


def test_empty_database_has_designed_empty_states(client, admin_user):
    html = dashboard_html(client, admin_user)
    # Zeros are numeric facts, dressed as archival notices — never bare.
    assert "dt>Active Clients</dt><dd>0</dd>" in html
    assert "ledger-empty" in html
    assert "Queue clear" in html
    assert "Finance / clear" in html
    assert "Ledger empty" in html
    assert "No charted activity" in html


def test_work_projects_table_uses_real_data(client, admin_user):
    owner = make_client()
    project = make_project(owner, name="Portal", status="ACTIVE")
    token = login(client)[1]
    opost(
        client, f"/admin/ops/projects/{project.id}/milestones", token,
        {"name": "Design", "description": "", "due_date": ""},
    )
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "Portal" in html
    assert "Acme Owner" in html
    assert f"/admin/crm/clients/{owner.id}" in html


def test_finance_overview_calculates_real_totals(client, admin_user):
    owner = make_client()
    token = login(client)[1]
    opost(
        client, f"/admin/crm/clients/{owner.id}/invoices", token,
        {"amount": "1000.00", "project_id": "", "due_at": ""},
    )
    from app.models.operations import Invoice

    invoice = Invoice.query.one()
    opost(client, f"/admin/ops/invoices/{invoice.id}/payments", token,
          {"amount": "250.00", "reference": "", "notes": ""})
    html = client.get("/admin/dashboard").get_data(as_text=True)
    assert "1000.00" in html
    assert "750.00" in html  # outstanding = invoiced - paid
    assert "dt>Overdue</dt><dd>0</dd>" in html


def test_pipeline_links_to_real_filtered_view(client, admin_user):
    from tests.test_crm import make_lead

    make_lead(status="QUALIFIED")
    html = dashboard_html(client, admin_user)
    assert "/admin/crm/leads?status=QUALIFIED" in html
    assert "dt>QUALIFIED</dt><dd>1</dd>" in html


def test_commands_only_reference_real_routes(client, admin_user):
    html = dashboard_html(client, admin_user)
    for href in ("/admin/documents/new", "/admin/projects/new",
                 "/admin/crm", "/admin/crm/leads", "/admin/crm/contacts"):
        assert f'href="{href}"' in html


def test_admin_header_unchanged(client, admin_user):
    html = dashboard_html(client, admin_user)
    for href in ("/admin/dashboard", "/admin/projects",
                 "/admin/categories", "/admin/crm", "/admin/crm/leads",
                 "/admin/crm/contacts"):
        assert f'href="{href}"' in html
    assert "Portfolio Admin" in html
    assert "Log out" in html


def test_ledger_styles_in_admin_css(client):
    css = client.get("/static/css/admin.css").get_data(as_text=True)
    for selector in (".ledger-masthead", ".ledger-metrics", ".metric-index",
                     ".ledger-empty", ".ledger-bars", ".ledger-bar-fill",
                     ".ledger-chart-bar", ".ledger-actions"):
        assert selector in css, selector
    for token in ("#F1EBDD", "#11100D", "#D5CEC1", "#F0442E",
                  "#3047C7"):
        assert token in css, token
    # Rare lime is used as a tinted treatment (subtle by design).
    assert "#B7D52B" in css or "183, 210, 43" in css


def test_dashboard_has_no_javascript(client, admin_user):
    html = dashboard_html(client, admin_user)
    assert "<script" not in html
    assert "innerHTML" not in html
