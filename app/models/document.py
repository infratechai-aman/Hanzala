"""Freelancer document vault model (private operational documents).                     

Only metadata is stored (title, category, type, URL/path). No file
storage, no generated legal documents. Documents listed in LEGAL_TYPES
are templates and must be reviewed before use.
"""

from datetime import datetime, timezone

from app.models import db

DOCUMENT_CATEGORIES = {
    "CLIENT_PROJECT": "CLIENT & PROJECT",
    "PRICING_APPROVAL": "PRICING & APPROVAL",
    "PROJECT_EXECUTION": "PROJECT EXECUTION",
    "DELIVERY": "DELIVERY",
    "MONEY_ACCOUNTING": "MONEY & ACCOUNTING",
    "CLOSING": "CLOSING",
}

DOCUMENT_TYPES = {
    "CLIENT_PROJECT": [
        "Client Information / Client Intake Form",
        "Client Brief",
        "Project Scope Document",
        "Scope of Work (SOW)",
        "Project Proposal",
        "Service Agreement / Freelance Contract",
        "NDA — Non-Disclosure Agreement",
        "Terms & Conditions",
    ],
    "PRICING_APPROVAL": [
        "Quotation",
        "Estimate",
        "Proposal + Pricing Sheet",
        "PO — Purchase Order",
        "Work Authorization / Approval",
        "Deposit / Advance Payment Request",
    ],
    "PROJECT_EXECUTION": [
        "Project Timeline",
        "Milestone Schedule",
        "Due-Date / Deadline Tracker",
        "Deliverables Checklist",
        "Task List",
        "Revision Request Form",
        "Change Request / Scope Change Form",
        "Client Approval / Sign-off Form",
        "Meeting / Call Notes",
    ],
    "DELIVERY": [
        "Delivery Note",
        "Final Deliverables Checklist",
        "Client Acceptance / Completion Certificate",
        "Handover Document",
        "Credentials / Asset Handover Record",
    ],
    "MONEY_ACCOUNTING": [
        "Advance / Deposit Receipt",
        "Invoice / E-Bill",
        "Payment Receipt",
        "Payment Due Notice",
        "Late Payment Notice",
        "Credit Note / Refund Record",
        "Expense Record",
        "Client Payment Ledger",
    ],
    "CLOSING": [
        "Project Completion Report",
        "Final Sign-Off",
        "Warranty / Support Terms",
        "Testimonial Request",
        "Referral Request",
        "Client Offboarding Checklist",
    ],
}

DOCUMENT_STATUSES = ("DRAFT", "READY", "ARCHIVED")

# Document types that are templates only, never legal advice.
LEGAL_TYPES = {
    "Service Agreement / Freelance Contract",
    "NDA — Non-Disclosure Agreement",
    "Terms & Conditions",
}


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(30), nullable=False, index=True)
    doc_type = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    url_or_path = db.Column(db.String(2000), nullable=True)
    # Operational context: which client/work this record belongs to.
    document_number = db.Column(
        db.String(40), nullable=True, unique=True, index=True
    )
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    current_version_id = db.Column(
        db.Integer,
        db.ForeignKey("document_versions.id", use_alter=True),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    versions = db.relationship(
        "DocumentVersion",
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )
    current_version = db.relationship(
        "DocumentVersion",
        foreign_keys=[current_version_id],
        post_update=True,
        uselist=False,
    )

    @property
    def category_label(self):
        return DOCUMENT_CATEGORIES.get(self.category, self.category)

    @property
    def is_legal_template(self):
        return self.doc_type in LEGAL_TYPES
