"""Admin Media Vault: portfolio-wide media assets (CRUD + visibility).

Every route requires authentication; every mutation is POST-only under
global CSRF. Local uploads are validated (extension, MIME plausibility,
magic bytes, size) and stored under generated names in one dedicated
directory. External URLs must be http(s); only YouTube/Vimeo get
embeds — everything else renders as an outbound link.
"""

from flask import flash, redirect, render_template, request, url_for

from app.models import db
from app.models.media_vault import (
    MEDIA_CONTEXTS,
    MEDIA_TYPES,
    MEDIA_VISIBILITY,
    PortfolioMedia,
)
from app.models.project import Project
from app.routes.admin import admin_bp, login_required
from app.services.media_vault import (
    delete_local_file,
    intro_conflict,
    is_safe_external_url,
    remove_if_unreferenced,
    storage_status,
    store_upload,
)


@admin_bp.route("/media")
@login_required
def vault_list():
    context = request.args.get("context", "").strip().upper()
    visibility = request.args.get("visibility", "").strip().upper()
    query = PortfolioMedia.query
    if context:
        if context not in MEDIA_CONTEXTS:
            flash("Invalid context filter.", "error")
            return redirect(url_for("admin.vault_list"))
        query = query.filter_by(context=context)
    if visibility:
        if visibility not in MEDIA_VISIBILITY:
            flash("Invalid visibility filter.", "error")
            return redirect(url_for("admin.vault_list"))
        query = query.filter_by(visibility=visibility)
    items = query.order_by(
        PortfolioMedia.display_order, PortfolioMedia.created_at.desc()
    ).all()
    return render_template(
        "admin/media/list.html",
        items=items,
        contexts=MEDIA_CONTEXTS,
        visibilities=MEDIA_VISIBILITY,
        active_context=context,
        active_visibility=visibility,
        storage_status=storage_status,
    )


@admin_bp.route("/media/new", methods=["GET", "POST"])
@login_required
def vault_new():
    form = blank_media_form()
    errors = {}
    if request.method == "POST":
        form = read_media_form()
        errors = validate_media(form, is_new=True)
        if not errors:
            new_file = None
            try:
                item = build_media(form)
                if item.storage == "LOCAL":
                    new_file = item.location
                db.session.add(item)
                db.session.flush()
                if not guard_intro_unique(item):
                    db.session.rollback()
                    remove_if_unreferenced(new_file)
                    flash(
                        "An intro is already published; "
                        "archive it before publishing another.",
                        "error",
                    )
                    return render_template(
                        "admin/media/form.html",
                        form=form,
                        errors=errors,
                        media_types=MEDIA_TYPES,
                        contexts=MEDIA_CONTEXTS,
                        visibilities=MEDIA_VISIBILITY,
                        projects=project_choices(),
                    )
                db.session.commit()
            except ValueError as exc:
                db.session.rollback()
                remove_if_unreferenced(new_file)
                errors["file"] = str(exc)
            except Exception:
                db.session.rollback()
                remove_if_unreferenced(new_file)
                errors["file"] = "Could not save the media item."
        if errors:
            flash("Please fix the errors below.", "error")
        else:
            if item.context == "INTRO" and item.visibility != "PUBLISHED":
                item.visibility = "PUBLISHED"
                db.session.commit()
            flash("Media item created.", "success")
            return redirect(url_for("admin.vault_list"))
    return render_template(
        "admin/media/form.html",
        form=form,
        errors=errors,
        media_types=MEDIA_TYPES,
        contexts=MEDIA_CONTEXTS,
        visibilities=MEDIA_VISIBILITY,
        projects=project_choices(),
    )


@admin_bp.route("/media/<int:media_id>/edit", methods=["GET", "POST"])
@login_required
def vault_edit(media_id):
    item = db.get_or_404(PortfolioMedia, media_id)
    form = media_to_form(item)
    errors = {}
    if request.method == "POST":
        form = read_media_form()
        errors = validate_media(form, is_new=False, item=item)
        if not errors:
            old_location = item.location if item.storage == "LOCAL" else None
            new_location = old_location
            try:
                apply_media_form(item, form)
                new_location = (
                    item.location if item.storage == "LOCAL" else None
                )
                if not guard_intro_unique(item, exclude_id=item.id):
                    db.session.rollback()
                    if new_location != old_location:
                        remove_if_unreferenced(new_location)
                    flash(
                        "An intro is already published; "
                        "archive it before publishing another.",
                        "error",
                    )
                    return render_template(
                        "admin/media/form.html",
                        form=form,
                        errors=errors,
                        item=item,
                        media_types=MEDIA_TYPES,
                        contexts=MEDIA_CONTEXTS,
                        visibilities=MEDIA_VISIBILITY,
                        projects=project_choices(),
                    )
                db.session.commit()
                # Old file goes only after the replacement is committed;
                # a failed commit keeps serving the previous file.
                if new_location != old_location:
                    if old_location:
                        delete_local_file(old_location)
            except ValueError as exc:
                db.session.rollback()
                if new_location != old_location:
                    remove_if_unreferenced(new_location)
                errors["file"] = str(exc)
            except Exception:
                db.session.rollback()
                if new_location != old_location:
                    remove_if_unreferenced(new_location)
                errors["file"] = "Could not save the media item."
        if errors:
            flash("Please fix the errors below.", "error")
        else:
            flash("Media item updated.", "success")
            return redirect(url_for("admin.vault_list"))
    return render_template(
        "admin/media/form.html",
        form=form,
        errors=errors,
        item=item,
        media_types=MEDIA_TYPES,
        contexts=MEDIA_CONTEXTS,
        visibilities=MEDIA_VISIBILITY,
        projects=project_choices(),
    )


@admin_bp.route("/media/<int:media_id>/visibility", methods=["POST"])
@login_required
def vault_visibility(media_id):
    item = db.get_or_404(PortfolioMedia, media_id)
    visibility = request.form.get("visibility", "").strip().upper()
    if visibility not in MEDIA_VISIBILITY:
        flash("Invalid visibility.", "error")
    elif (
        visibility == "PUBLISHED"
        and item.context == "INTRO"
        and intro_conflict(exclude_id=item.id) is not None
    ):
        flash(
            "An intro is already published; archive it first.", "error"
        )
    else:
        item.visibility = visibility
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Could not change visibility.", "error")
            return redirect(url_for("admin.vault_list"))
        flash(f"Visibility set to {visibility}.", "success")
    return redirect(url_for("admin.vault_list"))


@admin_bp.route("/media/<int:media_id>/delete", methods=["POST"])
@login_required
def vault_delete(media_id):
    item = db.get_or_404(PortfolioMedia, media_id)
    location = item.location if item.storage == "LOCAL" else None
    db.session.delete(item)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not delete the media item.", "error")
        return redirect(url_for("admin.vault_list"))
    # Physical file removal is best-effort and strictly scoped, and it
    # respects other references: a project record may point at the same
    # vault file, in which case the bytes must survive this delete.
    if location:
        remove_if_unreferenced(location)
    flash("Media item deleted.", "success")
    return redirect(url_for("admin.vault_list"))


def guard_intro_unique(item, exclude_id=None):
    """App-level single-published-INTRO guard (DB index backs it too)."""
    if item.context == "INTRO" and item.visibility == "PUBLISHED":
        if intro_conflict(exclude_id=exclude_id or item.id) is not None:
            return False
    return True


def project_choices():
    return Project.query.order_by(Project.display_order).all()


def blank_media_form():
    return {
        "title": "", "caption": "", "media_type": "IMAGE",
        "source": "upload", "external_url": "", "alt_text": "",
        "poster": "", "context": "WORK", "project_id": "",
        "visibility": "DRAFT", "display_order": "0",
    }


def media_to_form(item):
    return {
        "title": item.title,
        "caption": item.caption or "",
        "media_type": item.media_type,
        "source": "external" if item.storage == "EXTERNAL" else "upload",
        "external_url": item.location if item.storage == "EXTERNAL" else "",
        "alt_text": item.alt_text or "",
        "poster": item.poster or "",
        "context": item.context,
        "project_id": str(item.project_id or ""),
        "visibility": item.visibility,
        "display_order": str(item.display_order),
    }


def read_media_form():
    return {
        "title": request.form.get("title", "").strip(),
        "caption": request.form.get("caption", "").strip(),
        "media_type": request.form.get("media_type", "").strip().upper(),
        "source": request.form.get("source", "upload").strip().lower(),
        "external_url": request.form.get("external_url", "").strip(),
        "alt_text": request.form.get("alt_text", "").strip(),
        "poster": request.form.get("poster", "").strip(),
        "context": request.form.get("context", "WORK").strip().upper(),
        "project_id": request.form.get("project_id", "").strip(),
        "visibility": request.form.get("visibility", "DRAFT").strip().upper(),
        "display_order": request.form.get("display_order", "0").strip(),
    }


def validate_media(form, is_new, item=None):
    """Server-side validation; returns field -> message dict."""
    errors = {}
    if not form["title"]:
        errors["title"] = "Title is required."
    elif len(form["title"]) > 200:
        errors["title"] = "Title is too long."
    if form["media_type"] not in MEDIA_TYPES:
        errors["media_type"] = "Select a valid media type."
    if form["visibility"] not in MEDIA_VISIBILITY:
        errors["visibility"] = "Select a valid visibility."
    if form["context"] not in MEDIA_CONTEXTS:
        errors["context"] = "Select a valid context."
    if len(form["alt_text"]) > 255:
        errors["alt_text"] = "Alt text is too long."
    if len(form["poster"]) > 2000:
        errors["poster"] = "Poster URL is too long."
    elif form["poster"] and not is_safe_external_url(form["poster"]):
        errors["poster"] = "Poster must be an http(s) URL."
    try:
        order = int(form["display_order"] or "0")
        if order < 0 or order > 9999:
            raise ValueError
    except ValueError:
        errors["display_order"] = "Display order must be 0–9999."
    project_id = None
    if form["project_id"]:
        try:
            project_id = int(form["project_id"])
        except ValueError:
            project_id = None
        if project_id is None or db.session.get(Project, project_id) is None:
            errors["project_id"] = "Selected project does not exist."
    if form["context"] == "PROJECT" and project_id is None and not errors.get(
        "project_id"
    ):
        errors["project_id"] = "Project context needs a project."
    if form["media_type"] == "EXTERNAL_URL":
        if not form["external_url"]:
            errors["external_url"] = "External URL is required."
        elif not is_safe_external_url(form["external_url"]):
            errors["external_url"] = "URL must start with http(s)://."
    elif form["source"] == "external":
        if not form["external_url"]:
            errors["external_url"] = "External URL is required."
        elif not is_safe_external_url(form["external_url"]):
            errors["external_url"] = "URL must start with http(s)://."
    elif is_new:
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            errors["file"] = "Choose a file to upload."
    return errors


def build_media(form):
    """Construct an unsaved item; uploads persist during flush."""
    location, storage = resolve_location(form, item=None)
    return PortfolioMedia(
        title=form["title"],
        caption=form["caption"] or None,
        media_type=form["media_type"],
        storage=storage,
        location=location,
        alt_text=form["alt_text"] or None,
        poster=form["poster"] or None,
        context=form["context"],
        project_id=int(form["project_id"]) if form["project_id"] else None,
        visibility=form["visibility"],
        display_order=int(form["display_order"] or "0"),
    )


def apply_media_form(item, form):
    """Apply edits; a replacement upload swaps the stored file.

    The old file is NOT removed here — the caller deletes it only after
    a successful commit, so a failed save keeps serving the previous
    file instead of leaving a row that 404s.
    """
    location, storage = resolve_location(form, item=item)
    item.title = form["title"]
    item.caption = form["caption"] or None
    item.media_type = form["media_type"]
    item.storage = storage
    item.location = location
    item.alt_text = form["alt_text"] or None
    item.poster = form["poster"] or None
    item.context = form["context"]
    item.project_id = int(form["project_id"]) if form["project_id"] else None
    item.visibility = form["visibility"]
    item.display_order = int(form["display_order"] or "0")


def resolve_location(form, item):
    """Return (location, storage) for a create/edit form.

    EXTERNAL_URL types and explicit external sources use the validated
    URL. Otherwise a replacement upload is stored (raising ValueError
    on validation failure); edits without a new file keep the row.
    """
    if form["media_type"] == "EXTERNAL_URL" or form["source"] == "external":
        return form["external_url"], "EXTERNAL"
    upload = request.files.get("file")
    if upload is not None and upload.filename:
        return store_upload(upload, form["media_type"]), "LOCAL"
    if item is not None and item.storage == "LOCAL":
        return item.location, "LOCAL"
    raise ValueError("Choose a file to upload.")

