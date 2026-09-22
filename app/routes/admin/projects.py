"""Admin project management: CRUD plus link/media metadata.

Links and media are managed from the project detail page via small
POST forms (create/update/delete each). `file_path` is stored metadata
only — it is never opened or served from the filesystem here.
"""

from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for

from app.models import db
from app.models.project import Project, ProjectCategory, ProjectLink, ProjectMedia
from app.routes.admin import admin_bp, login_required


@admin_bp.route("/projects", methods=["GET"])
@login_required
def project_list():
    projects = Project.query.order_by(Project.display_order.desc()).all()
    return render_template(
        "admin/projects/list.html",
        projects=projects,
    )


@admin_bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    ensure_categories()
    form = blank_project_form()
    errors = {}
    if request.method == "POST":
        form = read_project_form()
        errors = validate_project_form(form)
        if not errors:
            project = Project(
                title=form["title"],
                slug=form["slug"],
                category_id=form["category_id"] or None,
                short_description=form["short_description"] or None,
                description=form["description"] or None,
                status=form["status"],
                role=form["role"] or None,
                problem=form["problem"] or None,
                why=form["why"] or None,
                system_description=form["system_description"] or None,
                technical_details=form["technical_details"] or None,
                decisions=form["decisions"] or None,
                result=form["result"] or None,
                proof=form["proof"] or None,
                learning=form["learning"] or None,
                limitations=form["limitations"] or None,
                next_steps=form["next_steps"] or None,
                is_featured=form["is_featured"],
                display_order=form["display_order"],
            )
            db.session.add(project)
            db.session.flush()
            for link_data in form.get("links", []):
                link = ProjectLink.query.filter_by(
                    project_id=project.id, url=link_data["url"]
                ).first()
                link_values = {
                    "label": link_data["label"],
                    "link_type": link_data.get("link_type"),
                    "display_order": link_data.get("display_order", 0),
                }
                if link is None:
                    db.session.add(ProjectLink(project_id=project.id, **link_values,
                                               url=link_data["url"]))
                    counts["created"] += 1
                elif _apply(link, link_values):
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
            for media_data in form.get("media", []):
                media = ProjectMedia.query.filter_by(
                    project_id=project.id, file_path=media_data["file_path"]
                ).first()
                values = {
                    "media_type": media_data["media_type"],
                    "alt_text": media_data["alt_text"],
                    "caption": media_data["caption"],
                    "display_order": media_data["display_order"],
                    "is_primary": media_data["is_primary"],
                }
                if media is None:
                    db.session.add(ProjectMedia(
                        project_id=project.id, file_path=media_data["file_path"], **values
                    ))
                    counts["created"] += 1
                elif _apply(media, values):
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
            db.session.commit()
            flash("Project created.", "success")
            return redirect(url_for("admin.project_list"))
        flash("Please fix the errors below.", "error")
    return render_template(
        "admin/projects/form.html",
        form=form,
        errors=errors,
        categories=PROJECT_CATEGORIES,
    )


@admin_bp.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = db.get_or_404(Project, project_id)
    return render_template(
        "admin/projects/detail.html",
        project=project,
    )


@admin_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id):
    ensure_categories()
    project = db.get_or_404(Project, project_id)
    form = project_to_form(project)
    errors = {}
    if request.method == "POST":
        form = read_project_form()
        errors = validate_project_form(form)
        if not errors:
            project.title = form["title"]
            project.slug = form["slug"]
            project.category_id = form["category_id"] or None
            project.short_description = form["short_description"] or None
            project.description = form["description"] or None
            project.status = form["status"]
            project.role = form["role"] or None
            project.problem = form["problem"] or None
            project.why = form["why"] or None
            project.system_description = form["system_description"] or None
            project.technical_details = form["technical_details"] or None
            project.decisions = form["decisions"] or None
            project.result = form["result"] or None
            project.proof = form["proof"] or None
            project.learning = form["learning"] or None
            project.limitations = form["limitations"] or None
            project.next_steps = form["next_steps"] or None
            project.is_featured = form["is_featured"]
            project.display_order = form["display_order"]
            # Handle media updates
            for media_data in form.get("media", []):
                media = ProjectMedia.query.filter_by(
                    project_id=project.id, file_path=media_data["file_path"]
                ).first()
                values = {
                    "media_type": media_data["media_type"],
                    "alt_text": media_data["alt_text"],
                    "caption": media_data["caption"],
                    "display_order": media_data["display_order"],
                    "is_primary": media_data["is_primary"],
                }
                if media is None:
                    db.session.add(ProjectMedia(
                        project_id=project.id, file_path=media_data["file_path"], **values
                    ))
                elif _apply(media, values):
                    pass  # updated in place
                # Remove media if not in form
                else:
                    db.session.delete(media)
            # Handle link updates
            for link_data in form.get("links", []):
                link = ProjectLink.query.filter_by(
                    project_id=project.id, url=link_data["url"]
                ).first()
                link_values = {
                    "label": link_data["label"],
                    "link_type": link_data.get("link_type"),
                    "display_order": link_data.get("display_order", 0),
                }
                if link is None:
                    db.session.add(ProjectLink(project_id=project.id, **link_values,
                                               url=link_data["url"]))
                elif _apply(link, link_values):
                    pass  # updated in place
                # Remove link if not in form
                else:
                    db.session.delete(link)
            db.session.commit()
            flash("Project updated.", "success")
            return redirect(url_for("admin.project_detail", project_id=project.id))
        flash("Please fix the errors below.", "error")
    return render_template(
        "admin/projects/form.html",
        form=form,
        errors=errors,
        categories=PROJECT_CATEGORIES,
    )


@admin_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def project_delete(project_id):
    project = db.get_or_404(Project, project_id)
    # Cascade: links and media are deleted via cascade
    db.session.delete(project)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not delete the project.", "error")
        return redirect(
            url_for("admin.project_list")
        )
    flash("Project deleted.", "success")
    return redirect(url_for("admin.project_list"))


def blank_project_form():
    return {
        "title": "", "slug": "", "category_id": "",
        "short_description": "", "description": "",
        "status": "COMPLETED", "role": "",
        "problem": "", "why": "", "system_description": "",
        "technical_details": "", "decisions": "", "result": "",
        "proof": "", "learning": "", "limitations": "",
        "next_steps": "", "is_featured": False, "display_order": "0",
    }


def project_to_form(project):
    return {
        "title": project.title,
        "slug": project.slug or "",
        "category_id": str(project.category_id) if project.category_id else "",
        "short_description": project.short_description or "",
        "description": project.description or "",
        "status": project.status,
        "role": project.role or "",
        "problem": project.problem or "",
        "why": project.why or "",
        "system_description": project.system_description or "",
        "technical_details": project.technical_details or "",
        "decisions": project.decisions or "",
        "result": project.result or "",
        "proof": project.proof or "",
        "learning": project.learning or "",
        "limitations": project.limitations or "",
        "next_steps": project.next_steps or "",
        "is_featured": project.is_featured,
        "display_order": str(project.display_order),
    }


def read_project_form():
    return {
        "title": request.form.get("title", "").strip(),
        "slug": request.form.get("slug", "").strip(),
        "category_id": request.form.get("category_id", "").strip(),
        "short_description": request.form.get("short_description", "").strip(),
        "description": request.form.get("description", "").strip(),
        "status": request.form.get("status", "").strip().upper(),
        "role": request.form.get("role", "").strip(),
        "problem": request.form.get("problem", "").strip(),
        "why": request.form.get("why", "").strip(),
        "system_description": request.form.get("system_description", "").strip(),
        "technical_details": request.form.get("technical_details", "").strip(),
        "decisions": request.form.get("decisions", "").strip(),
        "result": request.form.get("result", "").strip(),
        "proof": request.form.get("proof", "").strip(),
        "learning": request.form.get("learning", "").strip(),
        "limitations": request.form.get("limitations", "").strip(),
        "next_steps": request.form.get("next_steps", "").strip(),
        "is_featured": request.form.get("is_featured") == "on",
        "display_order": request.form.get("display_order", "0").strip(),
    }


def validate_project_form(form):
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
    if form["category_id"] and not db.session.get(ProjectCategory, int(form["category_id"])):
        errors["category_id"] = "Selected category does not exist."
    if not form["short_description"] and not form["description"]:
        errors["content"] = "Either short_description or description is required."
    if len(form["title"]) > 200:
        errors["title"] = "Title is too long."
    return errors


# Global project categories (populated at module load from seed data)
PROJECT_CATEGORIES = None


def ensure_categories():
    """Populate PROJECT_CATEGORIES from the database if not already set."""
    global PROJECT_CATEGORIES
    if PROJECT_CATEGORIES is not None:
        return
    PROJECT_CATEGORIES = [
        ProjectCategory.query.filter_by(slug=s).first()
        for s in ["built", "r-and-d"]
    ]