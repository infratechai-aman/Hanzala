"""Client Action Center: compose -> prepare -> confirm.

Flow per action: CLIENT -> WHY (purpose) -> ACTION -> CHANNEL ->
MESSAGE/DOCUMENT -> USER CONFIRMS. The system prepares messages and
opens the device app (WhatsApp/SMS/email); it never claims delivery.
Every prepared action is logged precisely as *prepared/opened* and
stored as a Followup row (purpose, channel, message, links).

All mutations are POST + login_required (global CSRF applies).
Documents are strictly scoped: a SEND action requires the document to
be READY and to belong to the client in scope.
"""

from flask import flash, redirect, render_template, request, url_for

from app.models import db
from app.models.crm import Client, Followup, Lead
from app.models.document import Document
from app.models.operations import ActivityEvent, ClientProject, Invoice
from app.routes.admin import admin_bp, login_required
from app.services.activity import log_event
from app.services.messages import (
    CHANNEL_LABELS,
    CHANNELS,
    FOLLOWUP_PURPOSES,
    PURPOSE_LABELS,
    SENDABLE_DOCUMENT_TYPES,
    build_context,
    digits_only,
    is_sendable,
    mailto_url,
    render_message,
    sendable_marker,
    sms_url,
    whatsapp_url,
)

CHANNEL_EVENTS = {
    "WHATSAPP": "WHATSAPP_PREPARED",
    "SMS": "SMS_PREPARED",
    "EMAIL": "EMAIL_PREPARED",
}

DOC_PURPOSE_BY_TYPE = {
    "Quotation": "QUOTATION",
    "Proposal": "PROPOSAL",
}


def _scope_or_404(kind, scope_id):
    """Resolve (contact, lead, client) for an action scope.

    kind "lead" -> lead's contact; kind "client" -> client contact plus
    the contact's most recent lead (follow-ups attach to a lead row).
    """
    if kind == "lead":
        lead = db.get_or_404(Lead, scope_id)
        return lead.contact, lead, None
    if kind == "client":
        client = db.get_or_404(Client, scope_id)
        contact = client.contact
        lead = (
            Lead.query.filter_by(contact_id=contact.id)
            .order_by(Lead.created_at.desc())
            .first()
        )
        return contact, lead, client
    return None, None, None  # unknown kind -> 404 below


def _scoped_document(document_id, client):
    """Document only if it belongs to the client in scope."""
    if not document_id or client is None:
        return None
    try:
        doc_id = int(document_id)
    except (TypeError, ValueError):
        return None
    return Document.query.filter_by(id=doc_id, client_id=client.id).first()


def _scoped_project(project_id, client):
    if not project_id or client is None:
        return None
    try:
        proj_id = int(project_id)
    except (TypeError, ValueError):
        return None
    return ClientProject.query.filter_by(id=proj_id, client_id=client.id).first()


def _scoped_invoice(invoice_id, client):
    if not invoice_id or client is None:
        return None
    try:
        inv_id = int(invoice_id)
    except (TypeError, ValueError):
        return None
    return Invoice.query.filter_by(id=inv_id, client_id=client.id).first()


def _public_document_url(document):
    """Shareable link only: http(s) url_or_path, else empty.

    A mailto link can never attach a local file, so private/local paths
    are never injected into messages — the confirm page covers those
    with an explicit manual-attach note instead.
    """
    location = (document.url_or_path or "").strip() if document else ""
    if location.startswith("http://") or location.startswith("https://"):
        return location
    return ""


def _message_context(contact, lead, client, project, document, invoice):
    """Template variables from real records only; missing -> empty."""
    from flask import url_for

    project_name = ""
    project_status = ""
    if project is not None:
        project_name = project.name or ""
        project_status = project.status or ""
    elif lead is not None and lead.service_interest:
        project_name = lead.service_interest
    service_name = lead.service_interest if lead is not None else ""
    service_name = service_name or ""
    business_name = ""
    if client is not None and client.company:
        business_name = client.company
    elif contact is not None and contact.company:
        business_name = contact.company
    project_fee = ""
    if lead is not None and lead.estimated_value is not None:
        project_fee = f"for {lead.estimated_value}"
    amount = ""
    amount_due = ""
    due_date = ""
    invoice_number = ""
    if invoice is not None:
        invoice_number = invoice.invoice_number or ""
        if invoice.amount is not None:
            amount = f"for {invoice.amount}"
        if invoice.outstanding:
            amount_due = f"Amount due: {invoice.outstanding}"
        if invoice.due_at:
            due_date = f"Due: {invoice.due_at.strftime('%Y-%m-%d')}"
    try:
        portfolio_url = url_for("public.index", _external=True)
    except Exception:
        portfolio_url = ""
    return build_context(
        client_name=contact.name if contact else "",
        business_name=business_name,
        project_name=project_name,
        service_name=service_name,
        document_name=(document.title if document else "") or "",
        document_number=(document.document_number if document else "") or "",
        document_url=_public_document_url(document),
        project_fee=project_fee,
        invoice_number=invoice_number,
        amount=amount,
        amount_due=amount_due,
        due_date=due_date,
        project_status=project_status,
        portfolio_url=portfolio_url,
    )


def sendable_slots_for(client, documents):
    """Per-type delivery slots: READY doc -> SEND; DRAFT -> not ready.

    Returns one row per SENDABLE_DOCUMENT_TYPES marker so the action
    center can show e.g. 'Quotation not ready' instead of a dead button.
    """
    by_marker = {}
    for document in documents or []:
        marker = sendable_marker(document.doc_type)
        if marker and document.status == "READY":
            current = by_marker.get(marker)
            if current is None or document.id > current.id:
                by_marker[marker] = document
    drafts = set()
    for document in documents or []:
        marker = sendable_marker(document.doc_type)
        if marker and document.status == "DRAFT" and marker not in by_marker:
            drafts.add(marker)
    slots = []
    for marker in SENDABLE_DOCUMENT_TYPES:
        slots.append({
            "marker": marker,
            "label": f"Send {marker}",
            "ready_doc": by_marker.get(marker),
            "draft_exists": marker in drafts,
            "client_id": client.id if client else None,
        })
    return slots


def _default_channel(contact):
    if contact and contact.phone:
        return "WHATSAPP"
    return "EMAIL"


def _default_project(client):
    if client is None:
        return None
    return (
        ClientProject.query.filter_by(client_id=client.id)
        .order_by(ClientProject.updated_at.desc())
        .first()
    )


def _compose_context(kind, scope_id, args):
    """Validate scope + params for the composer; returns dict or None."""
    contact, lead, client = _scope_or_404(kind, scope_id)
    if contact is None:
        return None
    purpose = (args.get("purpose") or "GENERAL").strip().upper()
    if purpose not in FOLLOWUP_PURPOSES:
        purpose = "GENERAL"
    channel = (args.get("channel") or "").strip().upper()
    if channel not in CHANNELS:
        channel = _default_channel(contact)
    document = _scoped_document(args.get("document_id"), client)
    project = _scoped_project(args.get("project_id"), client)
    invoice = _scoped_invoice(args.get("invoice_id"), client)
    if project is None:
        project = _default_project(client)
    if document is not None and not args.get("purpose"):
        # Suggest a purpose matching the document kind.
        for marker, mapped in DOC_PURPOSE_BY_TYPE.items():
            if marker.lower() in (document.doc_type or "").lower():
                purpose = mapped
                break
    context = _message_context(contact, lead, client, project, document, invoice)
    doc_blocked_reason = None
    if document is not None and document.status != "READY":
        doc_blocked_reason = (
            f"{document.document_number or document.title} is "
            f"{document.status} — only READY documents can be prepared."
        )
    elif document is not None and not is_sendable(document.doc_type):
        doc_blocked_reason = (
            f"{document.document_number or document.title} is an internal "
            "document type and cannot be shared with clients."
        )
    attachable = []
    if client is not None:
        attachable = [
            doc
            for doc in Document.query.filter_by(
                client_id=client.id, status="READY"
            )
            .order_by(Document.updated_at.desc())
            .all()
            if is_sendable(doc.doc_type)
        ]
    return {
        "kind": kind,
        "scope_id": scope_id,
        "contact": contact,
        "lead": lead,
        "client": client,
        "purpose": purpose,
        "channel": channel,
        "document": document,
        "project": project,
        "invoice": invoice,
        "context": context,
        "prefill": render_message(purpose, context),
        "purposes": [(p, PURPOSE_LABELS[p]) for p in FOLLOWUP_PURPOSES],
        "channels": [(c, CHANNEL_LABELS[c]) for c in CHANNELS],
        "has_phone": bool(contact.phone),
        "has_email": bool(contact.email),
        "attachable": attachable,
        "doc_public_url": _public_document_url(document),
        "doc_blocked_reason": doc_blocked_reason,
    }


@admin_bp.route("/crm/<kind>/<int:scope_id>/actions/compose")
@login_required
def action_compose(kind, scope_id):
    ctx = _compose_context(kind, scope_id, request.args)
    if ctx is None:
        return render_template("errors/404.html"), 404
    return render_template("admin/crm/action_compose.html", **ctx)


@admin_bp.route("/crm/<kind>/<int:scope_id>/actions/prepare", methods=["POST"])
@login_required
def action_prepare(kind, scope_id):
    contact, lead, client = _scope_or_404(kind, scope_id)
    if contact is None:
        return render_template("errors/404.html"), 404
    if lead is None:
        flash("Follow-up actions need a lead record; none exists here.", "error")
        return _back_to_scope(kind, scope_id, lead, client)

    form = request.form
    purpose = form.get("purpose", "").strip().upper()
    channel = form.get("channel", "").strip().upper()
    message = form.get("message", "").strip()
    scheduled_raw = form.get("scheduled_at", "").strip()
    document = _scoped_document(form.get("document_id"), client)
    project = _scoped_project(form.get("project_id"), client)
    invoice = _scoped_invoice(form.get("invoice_id"), client)

    if purpose not in FOLLOWUP_PURPOSES:
        flash("Select a valid purpose.", "error")
        return _recompose(kind, scope_id, form)
    if channel not in CHANNELS:
        flash("Select a valid channel.", "error")
        return _recompose(kind, scope_id, form)
    if channel in ("WHATSAPP", "SMS") and not contact.phone:
        flash(
            f"{CHANNEL_LABELS[channel]} needs a phone number; "
            "none is recorded for this contact.",
            "error",
        )
        return _recompose(kind, scope_id, form)
    if channel == "EMAIL" and not contact.email:
        flash("Email needs an address; none is recorded.", "error")
        return _recompose(kind, scope_id, form)
    if not message:
        flash("Message cannot be empty.", "error")
        return _recompose(kind, scope_id, form)
    if len(message) > 2000:
        flash("Message is too long (max 2000 characters).", "error")
        return _recompose(kind, scope_id, form)
    if document is not None and document.status != "READY":
        # DRAFT/ARCHIVED documents are never sent as current.
        flash("Only READY documents can be prepared for sharing.", "error")
        return _recompose(kind, scope_id, form)
    if document is not None and not is_sendable(document.doc_type):
        # Internal/admin-only types are never shared with clients.
        flash("That document type is internal and cannot be shared.", "error")
        return _recompose(kind, scope_id, form)
    # Local import: operations owns the datetime parser helper.
    from app.routes.admin.operations import _parse_datetime as _pdt

    scheduled_at = None
    if scheduled_raw:
        scheduled_at = _pdt(scheduled_raw)
        if scheduled_at == "invalid":
            flash("Scheduled date is invalid.", "error")
            return _recompose(kind, scope_id, form)

    summary = PURPOSE_LABELS[purpose]
    if document is not None:
        summary += f" — {document.document_number or document.title}"
    followup = Followup(
        lead_id=lead.id,
        scheduled_at=scheduled_at,
        note=summary[:500],
        purpose=purpose,
        channel=channel,
        message=message,
        project_id=project.id if project else None,
        document_id=document.id if document else None,
    )
    db.session.add(followup)
    db.session.flush()
    log_event(
        "FOLLOW_UP_PREPARED",
        f"{summary} prepared via {CHANNEL_LABELS[channel]}.",
        client_id=client.id if client else None,
        project_id=project.id if project else None,
        entity_type="followup",
        entity_id=followup.id,
    )
    log_event(
        CHANNEL_EVENTS[channel],
        f"{CHANNEL_LABELS[channel]} action prepared for {contact.name}. "
        "Delivery not verified.",
        client_id=client.id if client else None,
        project_id=project.id if project else None,
        entity_type="followup",
        entity_id=followup.id,
    )
    if document is not None:
        log_event(
            "DOCUMENT_PREPARED",
            f"{document.document_number or document.title} prepared for sharing. "
            "Delivery not verified.",
            client_id=client.id if client else None,
            project_id=project.id if project else None,
            entity_type="document",
            entity_id=document.id,
        )
    db.session.commit()
    flash("Action prepared. Open the channel to send it yourself.", "success")
    return redirect(url_for("admin.action_confirm", followup_id=followup.id))


def _recompose(kind, scope_id, form):
    """Re-render the composer with the user's entered values intact."""
    ctx = _compose_context(kind, scope_id, form)
    if ctx is None:
        return render_template("errors/404.html"), 404
    ctx["prefill"] = form.get("message", "")
    ctx["purpose"] = (form.get("purpose", "") or ctx["purpose"]).strip().upper()
    if ctx["purpose"] not in FOLLOWUP_PURPOSES:
        ctx["purpose"] = "GENERAL"
    channel = (form.get("channel", "") or "").strip().upper()
    ctx["channel"] = channel if channel in CHANNELS else ctx["channel"]
    return render_template("admin/crm/action_compose.html", **ctx)


def _back_to_scope(kind, scope_id, lead, client):
    if kind == "lead" and lead is not None:
        return redirect(url_for("admin.lead_detail", lead_id=lead.id))
    if kind == "client" and client is not None:
        return redirect(url_for("admin.client_detail", client_id=client.id))
    return render_template("errors/404.html"), 404


@admin_bp.route("/actions/confirm/<int:followup_id>")
@login_required
def action_confirm(followup_id):
    followup = db.get_or_404(Followup, followup_id)
    contact = followup.lead.contact if followup.lead else None
    client = None
    if contact is not None:
        client = Client.query.filter_by(contact_id=contact.id).first()
    document = None
    if followup.document_id:
        document = db.session.get(Document, followup.document_id)
    project = None
    if followup.project_id:
        project = db.session.get(ClientProject, followup.project_id)
    channel_link = ""
    channel_hint = ""
    if followup.channel == "WHATSAPP" and contact and contact.phone:
        channel_link = whatsapp_url(contact.phone, followup.message or "")
        channel_hint = (
            "Opens WhatsApp with the message filled in. "
            "You press send — the system cannot verify delivery."
        )
    elif followup.channel == "SMS" and contact and contact.phone:
        channel_link = sms_url(contact.phone, followup.message or "")
        channel_hint = (
            "Opens the device SMS app with the text filled in, "
            "where the device supports it."
        )
    elif followup.channel == "EMAIL" and contact and contact.email:
        subject = PURPOSE_LABELS.get(followup.purpose or "", "Follow-up")
        if document is not None:
            subject += f" — {document.document_number or document.title}"
        channel_link = mailto_url(contact.email, subject, followup.message or "")
        channel_hint = (
            "Opens your email client with recipient, subject and body "
            "filled in. You press send."
        )
    return render_template(
        "admin/crm/action_confirm.html",
        followup=followup,
        contact=contact,
        client=client,
        document=document,
        project=project,
        channel_link=channel_link,
        channel_hint=channel_hint,
        channel_label=CHANNEL_LABELS.get(followup.channel or "", "—"),
        purpose_label=PURPOSE_LABELS.get(followup.purpose or "", "—"),
        digits=digits_only(contact.phone) if contact and contact.phone else "",
        doc_public_url=_public_document_url(document),
        already_opened=_was_opened(followup.id),
    )


def _was_opened(followup_id):
    """True once the admin recorded opening the channel (explicit POST)."""
    return (
        ActivityEvent.query.filter_by(
            entity_type="followup",
            entity_id=followup_id,
            event_type="CHANNEL_OPENED",
        ).first()
        is not None
    )


@admin_bp.route("/actions/<int:followup_id>/opened", methods=["POST"])
@login_required
def action_opened(followup_id):
    """Record that the admin opened the channel app (not delivery).

    Clicking a wa.me/mailto/sms link cannot be observed server-side, so
    OPENED is recorded only through this explicit confirmation — never
    inferred, never called SENT.
    """
    followup = db.get_or_404(Followup, followup_id)
    contact = followup.lead.contact if followup.lead else None
    client = None
    if contact is not None:
        client = Client.query.filter_by(contact_id=contact.id).first()
    project = None
    if followup.project_id:
        project = db.session.get(ClientProject, followup.project_id)
    if not _was_opened(followup.id):
        log_event(
            "CHANNEL_OPENED",
            f"{CHANNEL_LABELS.get(followup.channel or '', 'Channel')} "
            f"opened for follow-up #{followup.id}. Delivery not verified.",
            client_id=client.id if client else None,
            project_id=project.id if project else None,
            entity_type="followup",
            entity_id=followup.id,
        )
        db.session.commit()
        flash("Recorded as opened (delivery not verified).", "success")
    else:
        flash("Already recorded as opened.", "success")
    return redirect(url_for("admin.action_confirm", followup_id=followup.id))


def contact_action_links(contact):
    """CALL/WHATSAPP/SMS/EMAIL targets from stored info (None if missing)."""
    phone = (contact.phone or "").strip() if contact else ""
    email = (contact.email or "").strip() if contact else ""
    return {
        "phone": phone,
        "email": email,
        "tel": f"tel:{phone}" if phone else None,
        "has_whatsapp": bool(phone),
        "has_sms": bool(phone),
        "has_email": bool(email),
    }


def build_suggestions(client, documents, invoices, projects):
    """Context-aware next actions: only states that actually exist.

    Each suggestion names WHY (reason), WHAT (purpose + optional
    document/project/invoice) — never a bare "contact client".
    """
    suggestions = []
    for invoice in invoices or []:
        if invoice.status == "OVERDUE":
            suggestions.append({
                "purpose": "PAYMENT",
                "label": f"Payment reminder — {invoice.invoice_number} overdue",
                "reason": f"Invoice {invoice.invoice_number} is overdue.",
                "document_id": None,
                "project_id": invoice.project_id,
                "invoice_id": invoice.id,
            })
    for document in documents or []:
        if document.status == "READY" and is_sendable(document.doc_type):
            suggestions.append({
                "purpose": _purpose_for_document(document),
                "label": (
                    f"Send {document.doc_type or 'document'} — "
                    f"{document.document_number or document.title}"
                ),
                "reason": (
                    f"{document.document_number or document.title} is READY "
                    "and awaiting the client."
                ),
                "document_id": document.id,
                "project_id": document.project_id,
                "invoice_id": None,
            })
    for project in projects or []:
        open_revisions = [
            r for r in (project.revisions or [])
            if r.status in ("OPEN", "IN_PROGRESS")
        ]
        if open_revisions:
            suggestions.append({
                "purpose": "REVISION",
                "label": f"Revision follow-up — {project.name}",
                "reason": (
                    f"{len(open_revisions)} revision request(s) open "
                    f"on {project.name}."
                ),
                "document_id": None,
                "project_id": project.id,
                "invoice_id": None,
            })
        elif project.status == "ACTIVE":
            suggestions.append({
                "purpose": "PROJECT_UPDATE",
                "label": f"Project update — {project.name}",
                "reason": f"{project.name} is active; share progress.",
                "document_id": None,
                "project_id": project.id,
                "invoice_id": None,
            })
    return suggestions[:6]


def _purpose_for_document(document):
    doc_type = (document.doc_type or "").lower()
    for marker, mapped in DOC_PURPOSE_BY_TYPE.items():
        if marker.lower() in doc_type:
            return mapped
    if "invoice" in doc_type:
        return "PAYMENT"
    return "APPROVAL"

