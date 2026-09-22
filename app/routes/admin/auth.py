"""Admin authentication: login (GET/POST) and logout (POST only)."""

from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_

from app.models import db
from app.models.admin_user import AdminUser
from app.routes.admin import admin_bp


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    # Authenticated admins have no business on the login page.
    if session.get("admin_user_id") is not None:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = None
        if identifier:
            user = AdminUser.query.filter(
                or_(
                    AdminUser.username == identifier,
                    AdminUser.email == identifier,
                )
            ).first()

        # One generic message: never reveal whether the identifier or
        # the password was wrong, or whether the account is inactive.
        if user is None or not user.is_active or not user.check_password(password):
            flash("Invalid credentials.", "error")
            return render_template("admin/login.html"), 200

        # Fresh session on login (mitigates session fixation).
        session.clear()
        session["admin_user_id"] = user.id
        session.permanent = True
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Logged in successfully.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("admin.login"))
