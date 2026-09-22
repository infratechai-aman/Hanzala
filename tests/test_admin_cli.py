"""Admin CLI tests: reset-admin password resets."""

from app.models import db
from app.models.admin_user import AdminUser
from tests.conftest import login


def invoke_reset(app, user_input):
    runner = app.test_cli_runner()
    return runner.invoke(args=["reset-admin"], input=user_input)


def test_reset_nonexistent_username(app):
    result = invoke_reset(app, "ghost\nnew-password\nnew-password\n")
    assert result.exit_code != 0
    assert "No admin user 'ghost' found" in result.output
    assert AdminUser.query.count() == 0


def test_reset_empty_password_rejected(app, admin_user):
    result = invoke_reset(app, "admin\n\n\n")
    assert result.exit_code != 0
    assert "must not be empty" in result.output
    db.session.refresh(admin_user)
    assert admin_user.check_password("correct-password") is True


def test_reset_mismatched_confirmation_rejected(app, admin_user):
    result = invoke_reset(app, "admin\nnew-one\nnew-two\n")
    assert result.exit_code != 0
    db.session.refresh(admin_user)
    assert admin_user.check_password("correct-password") is True
    assert admin_user.check_password("new-one") is False


def test_reset_success(app, admin_user):
    result = invoke_reset(app, "admin\ns3cret-new\ns3cret-new\n")
    assert result.exit_code == 0
    assert "Password reset for admin user 'admin'." in result.output
    assert "s3cret-new" not in result.output
    db.session.refresh(admin_user)
    assert admin_user.check_password("s3cret-new") is True
    assert admin_user.check_password("correct-password") is False


def test_reset_allows_login_with_new_password(client, admin_user):
    invoke_reset(client.application, "admin\ns3cret-new\ns3cret-new\n")
    response, _ = login(client, password="s3cret-new")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
