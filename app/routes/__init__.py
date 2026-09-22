"""Public portfolio routes."""

from flask import Blueprint, abort, render_template, send_file

from app.models.media_vault import PortfolioMedia
from app.services.media_vault import local_media_path

public_bp = Blueprint(
    "public",
    __name__,
)


@public_bp.route("/")
def index():
    """Render the public portfolio homepage."""
    intro_media = (
        PortfolioMedia.query.filter_by(
            visibility="PUBLISHED",
            context="INTRO",
        )
        .order_by(
            PortfolioMedia.display_order,
            PortfolioMedia.created_at.desc(),
        )
        .first()
    )

    return render_template(
        "public/index.html",
        intro_media=intro_media,
    )


@public_bp.route("/media/<path:location>")
def media(location):
    """Serve a published local portfolio media file."""
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

    return send_file(
        path,
        conditional=True,
    )
