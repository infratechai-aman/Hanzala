"""Reusable client message templates with safe variable substitution.

Templates use ``{{variable}}`` placeholders. Substitution is a plain
regex replace over an explicit allow-list — never Jinja rendering —
so an unknown or missing variable can never leak into output as
``{{undefined_variable}}``: it is replaced with an empty string and
leftover whitespace is collapsed.
"""

import re
from urllib.parse import quote

# Controlled vocabulary. Only these names are ever substituted.
ALLOWED_VARIABLES = (
    "client_name",
    "business_name",
    "project_name",
    "service_name",
    "document_name",
    "document_number",
    "document_url",
    "project_fee",
    "invoice_number",
    "amount",
    "amount_due",
    "due_date",
    "project_status",
    "developer_name",
    "portfolio_url",
)

# Single configurable classification: which vault doc_types are
# client-facing (sendable) vs internal/admin-only. Matched as
# case-insensitive substrings of Document.doc_type, in order.
SENDABLE_DOCUMENT_TYPES = (
    "Proposal",
    "Quotation",
    "Scope of Work",
    "Agreement",
    "NDA",
    "Invoice",
    "Payment Receipt",
    "Delivery",
    "Handoff",
    "Warranty",
    "Completion",
)

INTERNAL_DOCUMENT_TYPES = (
    "Access Register",
    "Meeting Notes",
    "Internal",
    "Communication Log",
)

DEVELOPER_NAME = "Hanzala"


def is_sendable(doc_type):
    """True when a vault doc_type is client-facing and sendable."""
    text = (doc_type or "").lower()
    if any(marker.lower() in text for marker in INTERNAL_DOCUMENT_TYPES):
        return False
    return any(marker.lower() in text for marker in SENDABLE_DOCUMENT_TYPES)


def sendable_marker(doc_type):
    """First matching sendable marker, or None (used for slot grouping)."""
    text = (doc_type or "").lower()
    for marker in SENDABLE_DOCUMENT_TYPES:
        if marker.lower() in text:
            return marker
    return None

FOLLOWUP_PURPOSES = (
    "GENERAL",
    "PROPOSAL",
    "QUOTATION",
    "APPROVAL",
    "PAYMENT",
    "PROJECT_UPDATE",
    "REVISION",
    "MEETING",
    "DOCUMENT_REQUEST",
    "CUSTOM",
)

PURPOSE_LABELS = {
    "GENERAL": "General follow-up",
    "PROPOSAL": "Proposal follow-up",
    "QUOTATION": "Quotation follow-up",
    "APPROVAL": "Approval request",
    "PAYMENT": "Payment reminder",
    "PROJECT_UPDATE": "Project update",
    "REVISION": "Revision request",
    "MEETING": "Meeting follow-up",
    "DOCUMENT_REQUEST": "Document request",
    "CUSTOM": "Custom",
}

CHANNELS = ("WHATSAPP", "SMS", "EMAIL")

CHANNEL_LABELS = {
    "WHATSAPP": "WhatsApp",
    "SMS": "SMS",
    "EMAIL": "Email",
}

MESSAGE_TEMPLATES = {
    "GENERAL": (
        "Hi {{client_name}}, just checking in regarding {{project_name}}. "
        "Please let me know if you need anything from my side."
    ),
    "PROPOSAL": (
        "Hi {{client_name}}, just following up regarding the proposal "
        "for {{project_name}}. Please let me know if you have any questions "
        "or would like to discuss anything."
    ),
    "QUOTATION": (
        "Hi {{client_name}}, I've prepared the quotation for {{project_name}}. "
        "Quotation: {{document_number}} {{project_fee}} {{document_url}} "
        "Please review it and let me know if you'd like to proceed."
    ),
    "APPROVAL": (
        "Hi {{client_name}}, the {{document_name}} is ready for your review "
        "and approval. {{document_url}} "
        "Please let me know once you've had a chance to review it."
    ),
    "PAYMENT": (
        "Hi {{client_name}}, just a quick reminder regarding {{invoice_number}} "
        "{{amount_due}} {{due_date}}. "
        "Please let me know if you need any information from my side."
    ),
    "PROJECT_UPDATE": (
        "Hi {{client_name}}, a quick update on {{project_name}}: "
        "current status is {{project_status}}."
    ),
    "REVISION": (
        "Hi {{client_name}}, regarding {{project_name}} — could you please "
        "share the revision details so I can proceed?"
    ),
    "MEETING": (
        "Hi {{client_name}}, confirming our meeting regarding {{project_name}}. "
        "Please let me know if the time still works for you."
    ),
    "DOCUMENT_REQUEST": (
        "Hi {{client_name}}, could you please review and confirm "
        "the {{document_name}} for {{project_name}}?"
    ),
    "CUSTOM": "",
}

_VARIABLE_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def render_message(purpose, context):
    """Render a purpose template against a context dict.

    Only ALLOWED_VARIABLES are substituted; anything missing or empty
    becomes an empty string. Whitespace is collapsed so absent data
    leaves clean sentences, never dangling placeholders.
    """
    template = MESSAGE_TEMPLATES.get(purpose, "")
    if not template:
        return ""
    safe = {
        name: str(context.get(name) or "").strip()
        for name in ALLOWED_VARIABLES
    }

    def _replace(match):
        return safe.get(match.group(1), "")

    rendered = _VARIABLE_RE.sub(_replace, template)
    return re.sub(r"\s+", " ", rendered).strip()


def build_context(client_name="", project_name="", service_name="",
                  document_name="", document_number="", document_url="",
                  project_fee="", invoice_number="",
                  amount="", amount_due="", due_date="", project_status="",
                  business_name="", developer_name=DEVELOPER_NAME,
                  portfolio_url=""):
    """Build a substitution context with exactly the allowed variables."""
    return {
        "client_name": client_name,
        "business_name": business_name,
        "project_name": project_name,
        "service_name": service_name,
        "document_name": document_name,
        "document_number": document_number,
        "document_url": document_url,
        "project_fee": project_fee,
        "invoice_number": invoice_number,
        "amount": amount,
        "amount_due": amount_due,
        "due_date": due_date,
        "project_status": project_status,
        "developer_name": developer_name,
        "portfolio_url": portfolio_url,
    }


def digits_only(phone):
    """Normalize a phone number for wa.me (digits only, no plus)."""
    return re.sub(r"\D", "", phone or "")


def whatsapp_url(phone, message):
    """Public wa.me share link with prefilled text (opens the app)."""
    return f"https://wa.me/{digits_only(phone)}?text={quote(message or '')}"


def sms_url(phone, message):
    """Device SMS URI with prefilled body (support varies by device)."""
    return f"sms:{phone}?body={quote(message or '')}"


def mailto_url(email, subject, message):
    """mailto link with subject and body (opens the mail client)."""
    return f"mailto:{email}?subject={quote(subject or '')}&body={quote(message or '')}"
