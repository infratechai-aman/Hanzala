"""Admin dashboard: operational record board from real database records.

Every number on the dashboard comes from a database query below —
nothing is hardcoded or seeded for display. Empty states are rendered
by the template as intentional archival notices.
"""

from datetime import timedelta
from decimal import Decimal

from flask import render_template
from sqlalchemy.orm import joinedload

from app.models import db
from app.models.admin_user import AdminUser
from app.models.crm import Client, Followup, Lead
from app.models.document import DOCUMENT_CATEGORIES, Document
from app.models.operations import (
    ActivityEvent,
    Approval,
    ClientProject,
    Deliverable,
    Invoice,
    Milestone,
    Payment,
    RevisionRequest,
)
from app.models.project import Project
from app.routes.admin.crm import utcnow_naive
from app.routes.admin import admin_bp, login_required

LEAD_PIPELINE_STATUSES = ("LEAD", "CONTACT", "QUALIFIED", "CLIENT", "LOST")

ACTIVITY_WINDOW_DAYS = 14


def _coalesce_zero(value):
    return value if value is not None else Decimal("0")


@admin_bp.route("/dashboard")
@login_required
def dashboard():
    now = utcnow_naive()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    open_followups = Followup.query.filter(
        Followup.completed_at.is_(None),
        Followup.scheduled_at.isnot(None),
    )
    overdue = open_followups.filter(
        Followup.scheduled_at < today_start
    ).order_by(Followup.scheduled_at).all()
    today = open_followups.filter(
        Followup.scheduled_at >= today_start,
        Followup.scheduled_at < today_end,
    ).order_by(Followup.scheduled_at).all()
    upcoming = open_followups.filter(
        Followup.scheduled_at >= today_end
    ).order_by(Followup.scheduled_at).limit(5).all()

    stats = {
        "leads": Lead.query.count(),
        "qualified": Lead.query.filter_by(status="QUALIFIED").count(),
        "clients": Client.query.count(),
        "followups_due": len(overdue) + len(today),
        "projects": Project.query.count(),
        "documents": Document.query.count(),
        # Operational metrics, each backed by a real query.
        "active_work_projects": ClientProject.query.filter_by(status="ACTIVE").count(),
        "pending_approvals": Approval.query.filter_by(status="PENDING").count(),
        "open_revisions": RevisionRequest.query.filter(
            RevisionRequest.status.in_(("OPEN", "IN_PROGRESS"))
        ).count(),
        "unpaid_invoices": Invoice.query.filter(
            Invoice.status.in_(("ISSUED", "PARTIALLY_PAID", "OVERDUE"))
        ).count(),
    }
    pipeline = [
        (status, Lead.query.filter_by(status=status).count())
        for status in LEAD_PIPELINE_STATUSES
    ]
    pipeline_max = max([count for _, count in pipeline] + [0])
    recent_leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()
    recent_projects = Project.query.order_by(Project.updated_at.desc()).limit(5).all()
    doc_stats = {
        "total": Document.query.count(),
        "draft": Document.query.filter_by(status="DRAFT").count(),
        "ready": Document.query.filter_by(status="READY").count(),
        "archived": Document.query.filter_by(status="ARCHIVED").count(),
    }
    docs_by_category = [
        (label, Document.query.filter_by(category=code).count())
        for code, label in DOCUMENT_CATEGORIES.items()
    ]
    recent_documents = Document.query.order_by(Document.updated_at.desc()).limit(5).all()

    # --- record-board aggregates (all real, all efficient) ---
    last_updated = _last_record_change()
    activity_days = _activity_by_day(now)
    recent_activity, actor_names = _recent_activity()
    work_projects = _work_project_rows()
    work_status_dist = _status_distribution(ClientProject, ClientProject.status)
    invoice_status_dist = _status_distribution(Invoice, Invoice.status)
    finance = _finance_overview()
    overdue_invoices = (
        Invoice.query.options(
            joinedload(Invoice.client).joinedload(Client.contact)
        )
        .filter_by(status="OVERDUE")
        .order_by(Invoice.due_at.asc())
        .limit(5)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        overdue=overdue,
        today=today,
        upcoming=upcoming,
        pipeline=pipeline,
        pipeline_max=pipeline_max,
        recent_leads=recent_leads,
        recent_projects=recent_projects,
        doc_stats=doc_stats,
        docs_by_category=docs_by_category,
        recent_documents=recent_documents,
        last_updated=last_updated,
        activity_days=activity_days,
        activity_max=max([count for _, count in activity_days] + [0]),
        recent_activity=recent_activity,
        actor_names=actor_names,
        work_projects=work_projects,
        work_status_dist=work_status_dist,
        invoice_status_dist=invoice_status_dist,
        finance=finance,
        overdue_invoices=overdue_invoices,
    )


def _last_record_change():
    """Most recent write across the operational tables (real metadata)."""
    stamps = [
        db.session.query(db.func.max(model.created_at)).scalar()
        for model in (Lead, Client, Document, Followup, ActivityEvent, Invoice)
    ]
    stamps = [stamp for stamp in stamps if stamp is not None]
    return max(stamps) if stamps else None


def _activity_by_day(now):
    """Event counts per day for the trailing window (oldest first)."""
    start = (now - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = (
        db.session.query(
            db.func.date(ActivityEvent.created_at).label("day"),
            db.func.count(ActivityEvent.id),
        )
        .filter(ActivityEvent.created_at >= start)
        .group_by(db.func.date(ActivityEvent.created_at))
        .all()
    )
    by_day = {str(day): count for day, count in rows}
    days = []
    for offset in range(ACTIVITY_WINDOW_DAYS):
        day = start + timedelta(days=offset)
        days.append((day.strftime("%d %b"), by_day.get(day.strftime("%Y-%m-%d"), 0)))
    return days


def _recent_activity(limit=12):
    """Latest audit events with actor names resolved in one extra query."""
    events = (
        ActivityEvent.query.order_by(
            ActivityEvent.created_at.desc(), ActivityEvent.id.desc()
        )
        .limit(limit)
        .all()
    )
    actor_ids = {event.actor_id for event in events if event.actor_id}
    names = {}
    if actor_ids:
        users = AdminUser.query.filter(AdminUser.id.in_(actor_ids)).all()
        names = {user.id: user.username for user in users}
    return events, names


def _work_project_rows(limit=8):
    """Active work overview: project + client + execution counts.

    Counts come from two grouped queries (no N+1 over milestones or
    deliverables); client names arrive via one joined load.
    """
    projects = (
        ClientProject.query.options(
            joinedload(ClientProject.client).joinedload(Client.contact)
        )
        .order_by(ClientProject.updated_at.desc())
        .limit(limit)
        .all()
    )
    project_ids = [project.id for project in projects]
    milestone_counts = {}
    deliverable_counts = {}
    if project_ids:
        milestone_counts = dict(
            db.session.query(
                Milestone.project_id, db.func.count(Milestone.id)
            )
            .filter(Milestone.project_id.in_(project_ids))
            .group_by(Milestone.project_id)
            .all()
        )
        deliverable_counts = dict(
            db.session.query(
                Deliverable.project_id, db.func.count(Deliverable.id)
            )
            .filter(Deliverable.project_id.in_(project_ids))
            .group_by(Deliverable.project_id)
            .all()
        )
    rows = []
    for project in projects:
        contact = project.client.contact if project.client else None
        rows.append(
            {
                "project": project,
                "client_name": contact.name if contact else "—",
                "client_id": project.client_id,
                "milestones": milestone_counts.get(project.id, 0),
                "deliverables": deliverable_counts.get(project.id, 0),
            }
        )
    return rows


def _status_distribution(model, column):
    """Status -> count pairs for model, ordered by count descending."""
    rows = (
        db.session.query(column, db.func.count(model.id))
        .group_by(column)
        .order_by(db.func.count(model.id).desc())
        .all()
    )
    return [(status or "—", count) for status, count in rows]


def _finance_overview():
    """Invoiced / paid / outstanding / overdue from real rows."""
    invoiced = _coalesce_zero(
        db.session.query(db.func.sum(Invoice.amount)).scalar()
    )
    paid = _coalesce_zero(
        db.session.query(db.func.sum(Payment.amount)).scalar()
    )
    overdue_count = Invoice.query.filter_by(status="OVERDUE").count()
    return {
        "invoiced": invoiced,
        "paid": paid,
        "outstanding": invoiced - paid,
        "overdue_count": overdue_count,
    }

