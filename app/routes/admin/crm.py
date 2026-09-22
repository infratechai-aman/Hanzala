"""Admin CRM: dashboard, leads, contacts, notes, follow-ups, conversion.

Every route requires authentication via `login_required`; every mutation
is POST-only (global CSRF protection applies). No CRM data is ever
rendered outside these admin templates.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

from flask import flash, redirect, render_template, request, url_for

from app.models import db
from app.models.crm import Client, Contact, Followup, Lead, Note
from app.routes.admin import admin_bp, login_required
from app.services.activity import log_event

# Lead lifecycle values. Anything else submitted is rejected.
LEAD_STATUSES = ("CONTACT", "LEAD", "QUALIFIED", "CLIENT", "LOST")
ACTIVE_LEAD_STATUSES = ("CONTACT", "LEAD", "QUALIFIED")

# Contact list filter states (derived, not a second status enum).
CONTACT_STATES = ("ALL", "NEW", "LEAD", "QUALIFIED", "CLIENT", "LOST")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _safe_next(default):
    """Redirect target for status forms: only internal admin paths."""
    for source in (request.form, request.args):
        target = (source.get("next") or "").strip()
        if target.startswith("/admin/") and "\n" not in target and "\r" not in target:
            return target
    return default


def utcnow_naive():
    # SQLite returns naive datetimes, so "now" comparisons use naive UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------ dashboard

@admin_bp.route("/crm")
@login_required
def crm_dashboard():
    now = utcnow_naive()
    stats = {
        "contacts": Contact.query.count(),
        "leads": Lead.query.count(),
        "qualified": Lead.query.filter_by(status="QUALIFIED").count(),
        "active": Lead.query.filter(Lead.status.in_(ACTIVE_LEAD_STATUSES)).count(),
        "clients": Client.query.count(),
        "followups_due": Followup.query.filter(
            Followup.completed_at.is_(None), Followup.scheduled_at <= now
        ).count(),
    }
    recent_leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()
    due_followups = (
        Followup.query.filter(
            Followup.completed_at.is_(None), Followup.scheduled_at <= now
        )
        .order_by(Followup.scheduled_at)
        .limit(10)
        .all()
    )
    clients = Client.query.order_by(Client.created_at.desc()).limit(10).all()
    return render_template(
        "admin/crm/dashboard.html",
        stats=stats,
        recent_leads=recent_leads,
        due_followups=due_followups,
        clients=clients,
    )


# ---------------------------------------------------------------- leads

@admin_bp.route("/crm/leads")
@login_required
def lead_list():
    status_filter = request.args.get("status", "").strip().upper()
    query = Lead.query
    if status_filter:
        if status_filter not in LEAD_STATUSES:
            flash("Invalid status filter.", "error")
            return redirect(url_for("admin.lead_list"))
        query = query.filter_by(status=status_filter)
    leads = query.order_by(Lead.created_at.desc()).all()
    return render_template(
        "admin/crm/leads.html",
        leads=leads,
        statuses=LEAD_STATUSES,
        active_filter=status_filter,
    )


@admin_bp.route("/crm/leads/<int:lead_id>")
@login_required
def lead_detail(lead_id):
    lead = db.get_or_404(Lead, lead_id)
    # Local import: actions owns the action-center context builders.
    from app.models.document import Document
    from app.routes.admin.actions import contact_action_links, sendable_slots_for
    from app.services.messages import is_sendable

    linked_client = Client.query.filter_by(contact_id=lead.contact_id).first()
    client_documents = []
    ready_documents = []
    if linked_client is not None:
        client_documents = (
            Document.query.filter_by(client_id=linked_client.id)
            .order_by(Document.updated_at.desc())
            .all()
        )
        ready_documents = [
            d for d in client_documents
            if d.status == "READY" and is_sendable(d.doc_type)
        ]
    return render_template(
        "admin/crm/lead_detail.html",
        lead=lead,
        statuses=LEAD_STATUSES,
        action_links=contact_action_links(lead.contact),
        linked_client=linked_client,
        ready_documents=ready_documents,
        sendable_slots=sendable_slots_for(linked_client, client_documents),
    )


@admin_bp.route("/crm/leads/<int:lead_id>/update", methods=["POST"])
@login_required
def lead_update(lead_id):
    lead = db.get_or_404(Lead, lead_id)
    status = request.form.get("status", "").strip().upper()
    service_interest = request.form.get("service_interest", "").strip()
    estimated_value_raw = request.form.get("estimated_value", "").strip()
    last_contacted_raw = request.form.get("last_contacted_at", "").strip()
    contact_now = request.form.get("contact_now") == "on"

    if status not in LEAD_STATUSES:
        flash("Invalid status.", "error")
        return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))
    if len(service_interest) > 200:
        flash("Service interest is too long.", "error")
        return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))

    estimated_value = None
    if estimated_value_raw:
        try:
            estimated_value = Decimal(estimated_value_raw)
        except InvalidOperation:
            flash("Estimated value must be a number.", "error")
            return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))
        if estimated_value < 0:
            flash("Estimated value cannot be negative.", "error")
            return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))

    last_contacted_at = lead.last_contacted_at
    if contact_now:
        last_contacted_at = datetime.now(timezone.utc)
    elif last_contacted_raw:
        try:
            last_contacted_at = datetime.strptime(last_contacted_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Last contacted date is invalid.", "error")
            return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))

    old_status = lead.status
    lead.status = status
    lead.service_interest = service_interest or None
    lead.estimated_value = estimated_value
    lead.last_contacted_at = last_contacted_at

    client = None
    if status == "CLIENT":
        client = convert_to_client(lead)
        # convert_to_client only adds; fetch the (possibly pre-existing) row.
        client = Client.query.filter_by(contact_id=lead.contact_id).first()

    db.session.flush()
    if old_status != status:
        log_event(
            "STATUS_CHANGED",
            f"Lead #{lead.id} status {old_status} -> {status}.",
            client_id=client.id if client else None,
            entity_type="lead",
            entity_id=lead.id,
        )
    if contact_now or last_contacted_raw:
        log_event(
            "FOLLOWUP_COMPLETED",
            f"Lead #{lead.id} contacted.",
            client_id=client.id if client else None,
            entity_type="lead",
            entity_id=lead.id,
        )

    db.session.commit()
    flash("Lead updated.", "success")
    return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))


@admin_bp.route("/crm/leads/<int:lead_id>/delete", methods=["POST"])
@login_required
def lead_delete(lead_id):
    lead = db.get_or_404(Lead, lead_id)
    # Deleting a lead removes its follow-ups and lead notes through the
    # existing cascades. The contact is never touched.
    db.session.delete(lead)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not delete the lead.", "error")
        return redirect(url_for("admin.lead_detail", lead_id=lead_id))
    flash("Lead deleted.", "success")
    return redirect(url_for("admin.lead_list"))


def convert_to_client(lead):
    """Create the Client for a lead's contact, unless one already exists.

    Conversion keeps the lead row — it never deletes anything.
    """
    existing = Client.query.filter_by(contact_id=lead.contact_id).first()
    if existing is None:
        db.session.add(
            Client(
                contact_id=lead.contact_id,
                company=lead.contact.company,
                notes=f"Converted from lead #{lead.id}.",
            )
        )


# ---------------------------------------------------------------- notes

@admin_bp.route("/crm/leads/<int:lead_id>/notes", methods=["POST"])
@login_required
def note_create(lead_id):
    lead = db.get_or_404(Lead, lead_id)
    content = request.form.get("content", "").strip()
    if not content:
        flash("Note cannot be empty.", "error")
    elif len(content) > 5000:
        flash("Note is too long (max 5000 characters).", "error")
    else:
        db.session.add(
            Note(content=content, lead_id=lead.id, contact_id=lead.contact_id)
        )
        db.session.flush()
        client = Client.query.filter_by(contact_id=lead.contact_id).first()
        log_event(
            "NOTE_ADDED",
            f"Note added to lead #{lead.id}.",
            client_id=client.id if client else None,
            entity_type="note",
        )
        db.session.commit()
        flash("Note added.", "success")
    return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))


# ------------------------------------------------------------ follow-ups

@admin_bp.route("/crm/leads/<int:lead_id>/followups", methods=["POST"])
@login_required
def followup_create(lead_id):
    lead = db.get_or_404(Lead, lead_id)
    scheduled_raw = request.form.get("scheduled_at", "").strip()
    note = request.form.get("note", "").strip()
    try:
        scheduled_at = datetime.strptime(scheduled_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Follow-up date is required and must be valid.", "error")
        return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))
    db.session.add(
        Followup(lead_id=lead.id, scheduled_at=scheduled_at, note=note or None)
    )
    db.session.flush()
    client = Client.query.filter_by(contact_id=lead.contact_id).first()
    log_event(
        "FOLLOWUP_SCHEDULED",
        f"Follow-up scheduled for lead #{lead.id}.",
        client_id=client.id if client else None,
        entity_type="followup",
    )
    db.session.commit()
    flash("Follow-up scheduled.", "success")
    return redirect(_safe_next(url_for("admin.lead_detail", lead_id=lead.id)))


@admin_bp.route("/crm/followups/<int:followup_id>/complete", methods=["POST"])
@login_required
def followup_complete(followup_id):
    followup = db.get_or_404(Followup, followup_id)
    if followup.completed_at is None:
        followup.completed_at = datetime.now(timezone.utc)
        client = Client.query.filter_by(
            contact_id=followup.lead.contact_id
        ).first()
        log_event(
            "FOLLOWUP_COMPLETED",
            f"Follow-up #{followup.id} completed.",
            client_id=client.id if client else None,
            entity_type="followup",
            entity_id=followup.id,
        )
        db.session.commit()
        flash("Follow-up marked completed.", "success")
    return redirect(url_for("admin.lead_detail", lead_id=followup.lead_id))


# -------------------------------------------------------------- contacts

def contact_state(contact):
    """Derived lifecycle state: NEW, LEAD, QUALIFIED, CLIENT, or LOST."""
    if contact.clients:
        return "CLIENT"
    statuses = [lead.status for lead in contact.leads]
    if not statuses:
        return "NEW"
    if "QUALIFIED" in statuses:
        return "QUALIFIED"
    if "LOST" in statuses and all(s == "LOST" for s in statuses):
        return "LOST"
    return "LEAD"


@admin_bp.route("/crm/contacts")
@login_required
def contact_list():
    from sqlalchemy.orm import joinedload

    state_filter = request.args.get("state", "ALL").strip().upper()
    if state_filter not in CONTACT_STATES:
        flash("Invalid state filter.", "error")
        return redirect(url_for("admin.contact_list"))
    contacts = (
        Contact.query.options(
            joinedload(Contact.leads), joinedload(Contact.clients)
        )
        .order_by(Contact.created_at.desc())
        .all()
    )
    states = {contact.id: contact_state(contact) for contact in contacts}
    if state_filter != "ALL":
        contacts = [c for c in contacts if states[c.id] == state_filter]
    counts = {state: 0 for state in CONTACT_STATES if state != "ALL"}
    for state in states.values():
        counts[state] += 1
    # Local import: action center owns the comm-link builders.
    from app.services.messages import mailto_url, whatsapp_url

    links = {}
    for contact in contacts:
        phone = (contact.phone or "").strip()
        links[contact.id] = {
            "tel": f"tel:{phone}" if phone else None,
            "wa": whatsapp_url(phone, "") if phone else None,
            "mail": mailto_url(contact.email, "", "") if contact.email else None,
        }
    return render_template(
        "admin/crm/contacts.html",
        contacts=contacts,
        states=states,
        links=links,
        counts=counts,
        active_filter=state_filter,
        lead_statuses=LEAD_STATUSES,
    )


@admin_bp.route("/crm/contacts/<int:contact_id>")
@login_required
def contact_detail(contact_id):
    from app.routes.admin.actions import contact_action_links
    from app.services.messages import mailto_url, whatsapp_url

    contact = db.get_or_404(Contact, contact_id)
    phone = (contact.phone or "").strip()
    return render_template(
        "admin/crm/contact_detail.html",
        contact=contact,
        state=contact_state(contact),
        action_links=contact_action_links(contact),
        wa_url=whatsapp_url(phone, "") if phone else None,
        mail_url=mailto_url(contact.email, "", "") if contact.email else None,
        lead_statuses=LEAD_STATUSES,
    )


@admin_bp.route("/crm/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    from app.routes.admin.actions import contact_action_links

    client = db.get_or_404(Client, client_id)
    return render_template(
        "admin/crm/client_detail.html",
        client=client,
        lead_statuses=LEAD_STATUSES,
    )


def validate_contact_fields(form):
    """Server-side validation for admin contact edits."""
    errors = {}
    if not form["name"]:
        errors["name"] = "Name is required."
    elif len(form["name"]) > 120:
        errors["name"] = "Name is too long."
    if not form["email"]:
        errors["email"] = "Email is required."
    elif len(form["email"]) > 255 or not EMAIL_RE.match(form["email"]):
        errors["email"] = "Enter a valid email address."
    if len(form["phone"]) > 50:
        errors["phone"] = "Phone number is too long."
    if len(form["company"]) > 200:
        errors["company"] = "Company name is too long."
    if len(form["message"]) > 5000:
        errors["message"] = "Message is too long (max 5000 characters)."
    if len(form["source"]) > 100:
        errors["source"] = "Source is too long."
    return errors


@admin_bp.route("/crm/contacts/<int:contact_id>/edit", methods=["POST"])
@login_required
def contact_update(contact_id):
    contact = db.get_or_404(Contact, contact_id)
    form = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "company": request.form.get("company", "").strip(),
        "message": request.form.get("message", "").strip(),
        "source": request.form.get("source", "").strip(),
    }
    errors = validate_contact_fields(form)
    if errors:
        for message in errors.values():
            flash(message, "error")
        return redirect(url_for("admin.contact_detail", contact_id=contact.id))
    contact.name = form["name"]
    contact.email = form["email"]
    contact.phone = form["phone"] or None
    contact.company = form["company"] or None
    contact.message = form["message"] or None
    contact.source = form["source"] or None
    log_event(
        "CONTACT_UPDATED",
        f"Contact #{contact.id} details updated.",
        entity_type="contact",
        entity_id=contact.id,
    )
    db.session.commit()
    flash("Contact updated.", "success")
    return redirect(
        _safe_next(url_for("admin.contact_detail", contact_id=contact.id))
    )


@admin_bp.route("/crm/contacts/<int:contact_id>/convert", methods=["GET", "POST"])
@login_required
def contact_convert(contact_id):
    """Review (GET) then create (POST) the Lead for a contact.

    Idempotent: a contact that already has a lead redirects to it —
    repeated clicks never create duplicates.
    """
    contact = db.get_or_404(Contact, contact_id)
    if contact.leads:
        lead = sorted(contact.leads, key=lambda l: l.id)[0]
        flash("This contact already has a lead.", "success")
        return redirect(url_for("admin.lead_detail", lead_id=lead.id))
    if request.method == "POST":
        service_interest = request.form.get("service_interest", "").strip()
        estimated_value_raw = request.form.get("estimated_value", "").strip()
        note = request.form.get("note", "").strip()
        if len(service_interest) > 200:
            flash("Service interest is too long.", "error")
            return redirect(url_for("admin.contact_convert", contact_id=contact.id))
        estimated_value = None
        if estimated_value_raw:
            try:
                estimated_value = Decimal(estimated_value_raw)
            except InvalidOperation:
                flash("Estimated value must be a number.", "error")
                return redirect(
                    url_for("admin.contact_convert", contact_id=contact.id)
                )
            if estimated_value < 0:
                flash("Estimated value cannot be negative.", "error")
                return redirect(
                    url_for("admin.contact_convert", contact_id=contact.id)
                )
        if len(note) > 5000:
            flash("Note is too long (max 5000 characters).", "error")
            return redirect(url_for("admin.contact_convert", contact_id=contact.id))
        lead = Lead(
            contact_id=contact.id,
            status="LEAD",
            service_interest=service_interest or None,
            estimated_value=estimated_value,
        )
        db.session.add(lead)
        db.session.flush()
        if note:
            db.session.add(
                Note(content=note, lead_id=lead.id, contact_id=contact.id)
            )
        log_event(
            "LEAD_CREATED",
            f"Lead #{lead.id} converted from contact #{contact.id}.",
            entity_type="lead",
            entity_id=lead.id,
        )
        db.session.commit()
        flash("Contact converted to lead.", "success")
        return redirect(url_for("admin.lead_detail", lead_id=lead.id))
    return render_template("admin/crm/contact_convert.html", contact=contact)


@admin_bp.route("/crm/contacts/<int:contact_id>/delete", methods=["POST"])
@login_required
def contact_delete(contact_id):
    """Delete only a bare contact. Anything with history is protected.

    Contact -> leads/clients/notes cascade on delete, so removing a
    contact with dependents would silently destroy CRM history. Refuse
    with an explanation instead.
    """
    contact = db.get_or_404(Contact, contact_id)
    blockers = []
    if contact.clients:
        blockers.append(f"{len(contact.clients)} client record(s)")
    if contact.leads:
        blockers.append(f"{len(contact.leads)} lead(s)")
    if contact.notes:
        blockers.append(f"{len(contact.notes)} note(s)")
    if blockers:
        flash(
            "Cannot delete this contact: it has "
            + ", ".join(blockers)
            + ". History is preserved; delete those records first.",
            "error",
        )
        return redirect(url_for("admin.contact_detail", contact_id=contact.id))
    db.session.delete(contact)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not delete the contact.", "error")
        return redirect(url_for("admin.contact_detail", contact_id=contact_id))
    flash("Contact deleted.", "success")
    return redirect(url_for("admin.contact_list"))
