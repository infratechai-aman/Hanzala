"""CRM models: contacts, leads, clients, followups, notes.

Lifecycle CONTACT -> LEAD -> QUALIFIED -> CLIENT -> PROJECT is only
represented here as data (`Lead.status` is a plain string). No workflow
logic or UI in this milestone.

`Note` may attach to a contact, lead, and/or client; at least one
should be set, but that is intentionally not enforced at the model
layer yet.
"""

from datetime import datetime, timezone

from app.models import db


class Contact(db.Model):
    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    phone = db.Column(db.String(50), nullable=True)
    company = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    leads = db.relationship(
        "Lead", back_populates="contact", cascade="all, delete-orphan"
    )
    clients = db.relationship(
        "Client", back_populates="contact", cascade="all, delete-orphan"
    )
    notes = db.relationship(
        "Note", back_populates="contact", cascade="all, delete-orphan"
    )


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(50), nullable=False, default="CONTACT", index=True)
    service_interest = db.Column(db.String(200), nullable=True)
    estimated_value = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_contacted_at = db.Column(db.DateTime, nullable=True)

    contact = db.relationship("Contact", back_populates="leads")
    followups = db.relationship(
        "Followup", back_populates="lead", cascade="all, delete-orphan"
    )
    lead_notes = db.relationship(
        "Note", back_populates="lead", cascade="all, delete-orphan"
    )


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    # Every client must reference the contact it originated from.
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contact = db.relationship("Contact", back_populates="clients")
    client_notes = db.relationship(
        "Note", back_populates="client", cascade="all, delete-orphan"
    )
    projects = db.relationship(
        "ClientProject", back_populates="client", cascade="all, delete-orphan"
    )
    documents = db.relationship("Document", backref="client", passive_deletes=True)
    invoices = db.relationship(
        "Invoice", backref="client", cascade="all, delete-orphan"
    )


class Followup(db.Model):
    __tablename__ = "followups"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(
        db.Integer,
        db.ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.Text, nullable=True)
    # Action-center fields: why this follow-up exists, via which
    # channel, with what prepared message, and what it relates to.
    # All nullable so every pre-existing follow-up keeps working.
    purpose = db.Column(db.String(30), nullable=True, index=True)
    channel = db.Column(db.String(20), nullable=True)
    message = db.Column(db.Text, nullable=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("client_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    lead = db.relationship("Lead", back_populates="followups")


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    lead_id = db.Column(
        db.Integer,
        db.ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contact = db.relationship("Contact", back_populates="notes")
    lead = db.relationship("Lead", back_populates="lead_notes")
    client = db.relationship("Client", back_populates="client_notes")
