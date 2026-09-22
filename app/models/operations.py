"""Client operations models: projects, document versions, approvals,
activity trail, execution records, acceptance, and finance foundation.

Design notes (kept deliberately simple):
- `ClientProject` is client work (name/status/dates). It is separate
  from the portfolio-showcase `Project` model, which is untouched.
- `Document` (existing vault table) gains operational context columns;
  history lives in `DocumentVersion`, approvals point at versions.
- `ActivityEvent` is append-only by convention: the app provides no
  edit/delete routes for it.
- Language rule: these records are internal application history, not
  legal proof. Templates must say "application activity record".
"""

from datetime import datetime, timezone

from app.models import db


def _utcnow():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Client work projects
# ------------------------------------------------------------------

CLIENT_PROJECT_STATUSES = (
    "PLANNING",
    "ACTIVE",
    "ON_HOLD",
    "COMPLETED",
    "CANCELLED",
)


class ClientProject(db.Model):
    __tablename__ = "client_projects"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="PLANNING", index=True)
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    client = db.relationship("Client", back_populates="projects")
    milestones = db.relationship(
        "Milestone", back_populates="project", cascade="all, delete-orphan"
    )
    deliverables = db.relationship(
        "Deliverable", back_populates="project", cascade="all, delete-orphan"
    )
    revisions = db.relationship(
        "RevisionRequest", back_populates="project", cascade="all, delete-orphan"
    )
    acceptances = db.relationship(
        "Acceptance", back_populates="project", cascade="all, delete-orphan"
    )


# ------------------------------------------------------------------
# Document versioning + approvals
# ------------------------------------------------------------------

VERSION_STATUSES = ("DRAFT", "SENT", "APPROVED", "REJECTED", "SUPERSEDED")

APPROVAL_TYPES = (
    "DOCUMENT_APPROVAL",
    "SCOPE_APPROVAL",
    "CLIENT_ACCEPTANCE",
    "FINAL_SIGN_OFF",
)


APPROVAL_STATUSES = ("PENDING", "APPROVED", "REJECTED", "REVOKED")


class DocumentVersion(db.Model):
    __tablename__ = "document_versions"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = db.Column(db.Integer, nullable=False)
    # Snapshot of the human-readable content at this version.
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    url_or_path = db.Column(db.String(2000), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"), nullable=True
    )
    superseded_at = db.Column(db.DateTime, nullable=True)
    superseded_by_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"), nullable=True
    )

    __table_args__ = (
        db.UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
    )

    document = db.relationship(
        "Document", back_populates="versions", foreign_keys=[document_id]
    )
    approvals = db.relationship(
        "Approval", back_populates="version", cascade="all, delete-orphan"
    )


class Approval(db.Model):
    __tablename__ = "approvals"

    id = db.Column(db.Integer, primary_key=True)
    document_version_id = db.Column(
        db.Integer,
        db.ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_type = db.Column(
        db.String(30), nullable=False, default="DOCUMENT_APPROVAL", index=True
    )
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=True)
    approver_name = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    version = db.relationship("DocumentVersion", back_populates="approvals")


# ------------------------------------------------------------------
# Activity trail (append-only by convention)
# ------------------------------------------------------------------

class ActivityEvent(db.Model):
    __tablename__ = "activity_events"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    actor_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"), nullable=True
    )
    event_type = db.Column(db.String(50), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)


# ------------------------------------------------------------------
# Project execution
# ------------------------------------------------------------------

MILESTONE_STATUSES = ("PLANNED", "IN_PROGRESS", "COMPLETED", "BLOCKED")

DELIVERABLE_STATUSES = ("PENDING", "DELIVERED", "ACCEPTED", "REJECTED")

REVISION_STATUSES = ("OPEN", "IN_PROGRESS", "COMPLETED", "REJECTED")


class Milestone(db.Model):
    __tablename__ = "milestones"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="PLANNED", index=True)
    due_date = db.Column(db.Date, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    project = db.relationship("ClientProject", back_populates="milestones")


class Deliverable(db.Model):
    __tablename__ = "deliverables"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    project = db.relationship("ClientProject", back_populates="deliverables")


class RevisionRequest(db.Model):
    __tablename__ = "revision_requests"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="OPEN", index=True)
    requested_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    project = db.relationship("ClientProject", back_populates="revisions")


# ------------------------------------------------------------------
# Client acceptance
# ------------------------------------------------------------------

ACCEPTANCE_TYPES = (
    "DELIVERABLE_ACCEPTANCE",
    "PROJECT_COMPLETION",
    "FINAL_SIGN_OFF",
)

ACCEPTANCE_STATUSES = ("PENDING", "ACCEPTED", "REJECTED")


class Acceptance(db.Model):
    __tablename__ = "acceptances"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deliverable_id = db.Column(
        db.Integer,
        db.ForeignKey("deliverables.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acceptance_type = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    client_name = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    project = db.relationship("ClientProject", back_populates="acceptances")
    deliverable = db.relationship("Deliverable")


# ------------------------------------------------------------------
# Finance foundation
# ------------------------------------------------------------------

INVOICE_STATUSES = (
    "DRAFT",
    "ISSUED",
    "PARTIALLY_PAID",
    "PAID",
    "OVERDUE",
    "CANCELLED",
)


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    issued_at = db.Column(db.DateTime, nullable=True)
    due_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    payments = db.relationship(
        "Payment", back_populates="invoice", cascade="all, delete-orphan"
    )

    @property
    def amount_paid(self):
        total = sum((p.amount for p in self.payments), 0)
        return total

    @property
    def outstanding(self):
        return (self.amount or 0) - self.amount_paid


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.DateTime, nullable=False, default=_utcnow)
    reference = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    invoice = db.relationship("Invoice", back_populates="payments")