"""Admin client operations: hub, commercial records, execution, finance.

All routes require authentication (`login_required`); all mutations are
POST-only under global CSRF protection. Every meaningful change writes
an `ActivityEvent` row — the chronological application activity record
for the client workspace. There are no edit/delete routes for events.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import flash, g, redirect, render_template, request, url_for

from app.models import db
from app.models.crm import Client, Note
from app.models.document import (
    DOCUMENT_CATEGORIES,
    DOCUMENT_STATUSES,
    DOCUMENT_TYPES,
    Document,
)
from app.routes.admin import admin_bp, login_required


def _utcnow():
    return datetime.now(timezone.utc)