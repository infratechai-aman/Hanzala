"""Admin category management.

Deleting a category preserves its projects: their `category_id` is
set to NULL explicitly (DB-agnostic, no reliance on FK enforcement).
"""

from flask import flash, redirect, render_template, request, url_for

from app.models import db
from app.models.project import Project, ProjectCategory
from app.routes.admin import admin_bp, login_required


@admin_bp.route("/categories")
@login_required
def category_list():
    categories = ProjectCategory.query.order_by(ProjectCategory.name).all()
    return render_template("admin/categories/list.html", categories=categories)


@admin_bp.route("/categories/new", methods=["GET", "POST"])
@login_required
def category_new():
    form = {"name": "", "slug": "", "description": ""}
    errors = {}
    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "slug": request.form.get("slug", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        errors = validate_category(form)
        if not errors:
            db.session.add(ProjectCategory(**form))
            db.session.commit()
            flash("Category created.", "success")
            return redirect(url_for("admin.category_list"))
        flash("Please fix the errors below.", "error")
    return render_template("admin/categories/form.html", form=form, errors=errors)


@admin_bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def category_edit(category_id):
    category = db.get_or_404(ProjectCategory, category_id)
    form = {
        "name": category.name,
        "slug": category.slug,
        "description": category.description or "",
    }
    errors = {}
    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "slug": request.form.get("slug", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        errors = validate_category(form, exclude_id=category.id)
        if not errors:
            category.name = form["name"]
            category.slug = form["slug"]
            category.description = form["description"] or None
            db.session.commit()
            flash("Category updated.", "success")
            return redirect(url_for("admin.category_list"))
        flash("Please fix the errors below.", "error")
    return render_template(
        "admin/categories/form.html", form=form, errors=errors, category=category
    )


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def category_delete(category_id):
    category = db.get_or_404(ProjectCategory, category_id)
    # Preserve projects: detach them before removing the category.
    Project.query.filter_by(category_id=category.id).update({"category_id": None})
    db.session.delete(category)
    db.session.commit()
    flash("Category deleted. Its projects were kept.", "success")
    return redirect(url_for("admin.category_list"))


def validate_category(form, exclude_id=None):
    """Server-side validation; returns a dict of field -> message."""
    errors = {}
    if not form["name"]:
        errors["name"] = "Name is required."
    if not form["slug"]:
        errors["slug"] = "Slug is required."

    for field in ("name", "slug"):
        if form[field]:
            existing = ProjectCategory.query.filter(
                getattr(ProjectCategory, field) == form[field]
            ).first()
            if existing is not None and existing.id != exclude_id:
                errors[field] = f"That {field} is already in use."
    return errors
