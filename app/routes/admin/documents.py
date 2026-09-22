"""Admin document vault: private freelancer documents (CRUD).

Every route requires authentication; every mutation is POST-only
(global CSRF protection applies). Documents are metadata only —
no file storage, no generated legal content.
"""

from flask import flash, redirect, render_template, request, url_for

from app.models import db
from app.models.document import (
    DOCUMENT_CATEGORIES,
    DOCUMENT_STATUSES,
    DOCUMENT_TYPES,
    Document,
)
from app.routes.admin import admin_bp, login_required


@admin_bp.route("/documents", methods=["GET"])
@login_required
def document_list():
    documents = Document.query.order_by(Document.display_at.desc()).all()
    return render_template(
        "admin/documents/list.html",
        documents=documents,
    )


@admin_bp.route("/documents/new", methods=["GET", "POST"])
@login_required
def document_new():
    form = blank_document_form()
    errors = {}
    if request.method == "POST":
        form = read_document_form()
        errors = validate_document_form(form)
        if not errors:
            document = Document(
                title=form["title"],
                slug=form["slug"],
                document_type=form["document_type"],
                status=form["status"],
                category_id=form["category_id"] or None,
                client_id=form["client_id"] or None,
                tags=form["tags"] or None,
                description=form["description"] or None,
                content_safe_summary=form["content_safe_summary"] or None,
                display_order=form["display_order"],
            )
            db.session.add(document)
            db.session.commit()
            flash("Document created.", "success")
            return redirect(url_for("admin.document_list"))
        flash("Please fix the errors below.", "error")
    return render_template(
        "admin/documents/form.html",
        form=form,
        errors=errors,
        document_types=DOCUMENT_TYPES,
        document_statuses=DOCUMENT_STATUSES,
    )


@admin_bp.route("/documents/<int:document_id>")
@login_required
def document_detail(document_id):
    document = db.get_or_404(Document, document_id)
    return render_template(
        "admin/documents/detail.html",
        document=document,
    )


@admin_bp.route("/documents/<int:document_id>/edit", methods=["GET", "POST"])
@login_required
def document_edit(document_id):
    document = db.get_or_404(Document, document_id)
    form = document_to_form(document)
    errors = {}
    if request.method == "POST":
        form = read_document_form()
        errors = validate_document_form(form)
        if not errors:
            document.title = form["title"]
            document.slug = form["slug"]
            document.document_type = form["document_type"]
            document.status = form["status"]
            document.category_id = form["category_id"] or None
            document.client_id = form["client_id"] or None
            document.tags = form["tags"] or None
            document.description = form["description"] or None
            document.content_safe_summary = form["content_safe_summary"] or None
            document.display_order = form["display_order"]
            db.session.commit()
            flash("Document updated.", "success")
            return redirect(url_for("admin.document_detail", document_id=document.id))
        flash("Please fix the errors below.", "error")
    return render_template(
        "admin/documents/form.html",
        form=form,
        errors=errors,
        document_types=DOCUMENT_TYPES,
        document_statuses=DOCUMENT_STATUSES,
    )


@admin_bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@login_required
def document_delete(document_id):
    document = db.get_or_404(Document, document_id)
    db.session.delete(document)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not delete the document.", "error")
        return redirect(url_for("admin.document_list"))
    flash("Document deleted.", "success")
    return redirect(url_for("admin.document_list"))


def blank_document_form():
    return {
        "title": "", "slug": "", "document_type": "",
        "status": "DRAFT", "category_id": "", "client_id": "",
        "tags": "", "description": "", "content_safe_summary": "",
        "display_order": "0",
    }


def document_to_form(document):
    return {
        "title": document.title,
        "slug": document.slug or "",
        "document_type": document.document_type or "",
        "status": document.status,
        "category_id": str(document.category_id) if document.category_id else "",
        "client_id": str(document.client_id) if document.client_id else "",
        "tags": document.tags or "",
        "description": document.description or "",
        "content_safe_summary": document.content_safe_summary or "",
        "display_order": str(document.display_order),
    }


def read_document_form():
    return {
        "title": request.form.get("title", "").strip(),
        "slug": request.form.get("slug", "").strip(),
        "document_type": request.form.get("document_type", "").strip(),
        "status": request.form.get("status", "").strip().upper(),
        "category_id": request.form.get("category_id", "").strip(),
        "client_id": request.form.get("client_id", "").strip(),
        "tags": request.form.get("tags", "").strip(),
        "description": request.form.get("description", "").strip(),
        "content_safe_summary": request.form.get("content_safe_summary", "").strip(),
        "display_order": request.form.get("display_order", "0").strip(),
    }


def validate_document_form(form):
    """Server-side validation; returns a dict of field -> message."""
    errors = {}
    if not form["title"]:
        errors["title"] = "Title is required."
    elif len(form["title"]) > 200:
        errors["title"] = "Title is too long."
    if not form["slug"]:
        errors["slug"] = "Slug is required."
    elif len(form["slug"]) > 220:
        errors["slug"] = "Slug is too long."
    if form["category_id"] and not db.session.get(
        "app.models.document.ProjectCategory", int(form["category_id"])
    ):
        errors["category_id"] = "Selected category does not exist."
    if not form["document_type"]:
        errors["document_type"] = "Document type is required."
    return errors