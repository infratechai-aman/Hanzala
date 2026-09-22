"""Public (visitor-facing) routes.

Read-only, except the contact form (POST /contact), which creates
Contact + Lead records. Only portfolio content models are queried here
— never AdminUser, and CRM records are only created, never listed.
"""

import re

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app.models import db
from app.models.crm import Contact, Lead
from app.models.experience import Experience
from app.models.learning import LearningItem
from app.models.project import Project, ProjectCategory, ProjectLink

public_bp = Blueprint("public", __name__)


@public_bp.route("/media/<path:location>")
def media(location):
    """Serve published local portfolio media safely."""
    from app.models.media_vault import PortfolioMedia
    from app.services.media_vault import local_media_path

    item = PortfolioMedia.query.filter_by(
        location=location,
        storage="LOCAL",
        visibility="PUBLISHED",
    ).first()

    if item is None:
        abort(404)

    path = local_media_path(item.location)

    if path is None:
        abort(404)

    return send_file(path, conditional=True)


@public_bp.route("/favicon.ico")
def favicon():
    """Serve favicon safely."""
    import os
    from flask import current_app, send_from_directory, Response
    try:
        return send_from_directory(
            os.path.join(current_app.root_path, "static", "images"),
            "hanzala-avatar.png",
            mimetype="image/png",
        )
    except Exception:
        return Response(status=204)


@public_bp.app_context_processor
def inject_elsewhere():
    """Verified external proof links (DB-driven, never fabricated).

    Available in all public templates for the footer and identity areas.
    Renders nothing when no such links exist.
    """
    try:
        links = (
            ProjectLink.query.filter(
                ProjectLink.link_type.in_(["demo", "code"])
            )
            .order_by(ProjectLink.display_order)
            .all()
        )
        return {"elsewhere_links": links}
    except Exception:
        return {"elsewhere_links": []}


PROJECT_ORDER = (Project.display_order, Project.created_at.desc())

# Fixed service-interest options for the contact form.
# Anything else submitted is rejected.
SERVICE_OPTIONS = [
    "Small business website",
    "Landing page",
    "Website improvement",
    "Lightweight business system",
    "Lead/contact workflow",
    "Custom web application",
    "Something else",
]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_contact(form):
    """Server-side validation for the public contact form."""
    errors = {}

    if not form["name"]:
        errors["name"] = "Name is required."
    elif len(form["name"]) > 120:
        errors["name"] = "Name is too long."

    if not form["email"]:
        errors["email"] = "Email is required."
    elif len(form["email"]) > 255 or not EMAIL_RE.match(form["email"]):
        errors["email"] = "Enter a valid email address."

    if not form["message"]:
        errors["message"] = "Message is required."
    elif len(form["message"]) > 5000:
        errors["message"] = "Message is too long (max 5000 characters)."

    if len(form["phone"]) > 50:
        errors["phone"] = "Phone number is too long."

    if len(form["company"]) > 200:
        errors["company"] = "Company name is too long."

    if len(form["source"]) > 100:
        errors["source"] = "Source is too long."

    if (
        form["service_interest"]
        and form["service_interest"] not in SERVICE_OPTIONS
    ):
        errors["service_interest"] = "Invalid service selected."

    return errors


@public_bp.route("/")
def index():
    try:
        featured = (
            Project.query.filter_by(is_featured=True)
            .order_by(*PROJECT_ORDER)
            .all()
        )
    except Exception:
        featured = []

    try:
        experiments = (
            Project.query.join(
                ProjectCategory,
                Project.category_id == ProjectCategory.id,
            )
            .filter(ProjectCategory.slug == "r-and-d")
            .order_by(*PROJECT_ORDER)
            .all()
        )
    except Exception:
        experiments = []

    try:
        selected_work = (
            Project.query.filter(
                Project.slug.in_(
                    ["estora", "umama-motors", "business-systems"]
                )
            )
            .order_by(*PROJECT_ORDER)
            .all()
        )
    except Exception:
        selected_work = []

    try:
        learning_items = (
            LearningItem.query.order_by(
                LearningItem.display_order,
                LearningItem.created_at.desc(),
            )
            .limit(4)
            .all()
        )
    except Exception:
        learning_items = []

    try:
        experiences = (
            Experience.query.order_by(
                Experience.display_order,
                Experience.created_at.desc(),
            )
            .limit(2)
            .all()
        )
    except Exception:
        experiences = []

    intro_media = None
    intro_embed = None
    try:
        from app.services.media_vault import provider_embed_url, published_intro
        intro_media = published_intro()
        intro_embed = (
            provider_embed_url(intro_media.location)
            if intro_media is not None
            and intro_media.storage == "EXTERNAL"
            else None
        )
    except Exception:
        pass

    return render_template(
        "public/index.html",
        featured=featured,
        selected_work=selected_work,
        experiments=experiments,
        learning_items=learning_items,
        experiences=experiences,
        intro_media=intro_media,
        intro_embed=intro_embed,
    )


@public_bp.route("/work")
def work():
    try:
        all_categories = (
            ProjectCategory.query
            .order_by(ProjectCategory.name)
            .all()
        )
    except Exception:
        all_categories = []

    built = next(
        (c for c in all_categories if c.slug == "built"),
        None,
    )

    rnd = next(
        (c for c in all_categories if c.slug == "r-and-d"),
        None,
    )

    others = [
        c for c in all_categories
        if c.slug not in ("built", "r-and-d")
    ]

    try:
        uncategorized = (
            Project.query
            .filter_by(category_id=None)
            .order_by(*PROJECT_ORDER)
            .all()
        )
    except Exception:
        uncategorized = []

    return render_template(
        "public/work.html",
        built=built,
        rnd=rnd,
        others=others,
        uncategorized=uncategorized,
    )


@public_bp.route("/work/<slug>")
def project_detail(slug):
    project = Project.query.filter_by(slug=slug).first_or_404()

    return render_template(
        "public/project_detail.html",
        project=project,
    )


@public_bp.route("/r-and-d")
def rnd():
    category = (
        ProjectCategory.query
        .filter_by(slug="r-and-d")
        .first_or_404()
    )

    try:
        projects = (
            Project.query
            .filter_by(category_id=category.id)
            .order_by(*PROJECT_ORDER)
            .all()
        )
    except Exception:
        projects = []

    return render_template(
        "public/rnd.html",
        category=category,
        projects=projects,
    )


@public_bp.route("/context")
def context():
    try:
        experiences = (
            Experience.query
            .order_by(
                Experience.display_order,
                Experience.created_at.desc(),
            )
            .all()
        )
    except Exception:
        experiences = []

    return render_template(
        "public/context.html",
        experiences=experiences,
    )


@public_bp.route("/learning")
def learning():
    try:
        items = (
            LearningItem.query
            .order_by(
                LearningItem.display_order,
                LearningItem.created_at.desc(),
            )
            .all()
        )
    except Exception:
        items = []

    return render_template(
        "public/learning.html",
        items=items,
    )


@public_bp.route("/process")
def process():
    return render_template("public/process.html")


@public_bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = {
        "name": "",
        "email": "",
        "phone": "",
        "company": "",
        "message": "",
        "source": "",
        "service_interest": "",
    }

    errors = {}

    if request.method == "POST":
        # Honeypot: bots fill it, humans never see it.
        if request.form.get("website", "").strip():
            flash(
                "Thanks — your message has been received.",
                "success",
            )
            return redirect(url_for("public.contact"))

        form = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "company": request.form.get("company", "").strip(),
            "message": request.form.get("message", "").strip(),
            "source": request.form.get("source", "").strip(),
            "service_interest": request.form.get(
                "service_interest",
                "",
            ).strip(),
        }

        errors = validate_contact(form)

        if not errors:
            contact = Contact(
                name=form["name"],
                email=form["email"],
                phone=form["phone"] or None,
                company=form["company"] or None,
                message=form["message"],
                source=form["source"] or None,
            )

            db.session.add(contact)
            db.session.flush()

            lead = Lead(
                contact_id=contact.id,
                status="LEAD",
                service_interest=form["service_interest"] or None,
            )

            db.session.add(lead)
            db.session.flush()

            from app.services.activity import log_event as _log

            _log(
                "LEAD_CREATED",
                f"Lead #{lead.id} created from the contact form.",
                entity_type="lead",
                entity_id=lead.id,
            )

            db.session.commit()

            flash(
                "Thanks — your message has been received.",
                "success",
            )

            return redirect(url_for("public.contact"))

        flash("Please fix the errors below.", "error")

    return render_template(
        "public/contact.html",
        form=form,
        errors=errors,
        service_options=SERVICE_OPTIONS,
    )