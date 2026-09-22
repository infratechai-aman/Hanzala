"""Secure admin panel blueprint.

Routes live in sibling modules (auth, dashboard, projects, categories)
and are imported below. `login_required` is the single gate every
data-management route must use.
"""

import functools

from flask import Blueprint, flash, g, redirect, session, url_for

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_required(view):
    """Redirect unauthenticated (or deactivated) users to the login page."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        # Local import avoids a hard dependency cycle at module load time.
        from app.models import db
        from app.models.admin_user import AdminUser

        user = None
        user_id = session.get("admin_user_id")
        if user_id is not None:
            user = db.session.get(AdminUser, user_id)
        if user is None or not user.is_active:
            # Drop only the auth key: clearing the whole session would
            # also wipe the CSRF token and break subsequent form posts.
            session.pop("admin_user_id", None)
            flash("Please log in to access the admin panel.", "error")
            return redirect(url_for("admin.login"))
        g.admin_user = user
        return view(*args, **kwargs)

    return wrapped


@admin_bp.before_request
def load_admin_user():
    """Expose the current admin (if any) to templates for nav display."""
    g.admin_user = None
    user_id = session.get("admin_user_id")
    if user_id is not None:
        # Local import: models must be loaded after the app package init.
        from app.models import db
        from app.models.admin_user import AdminUser

        user = db.session.get(AdminUser, user_id)
        if user is not None and user.is_active:
            g.admin_user = user


# Route modules attach their views to `admin_bp` on import.
from app.routes.admin import actions, auth, categories, crm, dashboard, documents, media_vault, operations, projects  # noqa: E402,F401
