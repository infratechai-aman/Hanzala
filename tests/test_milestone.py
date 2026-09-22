"""Milestone tests: project media rendering lifecycle + document action center.

Media: create project -> add media -> public page renders it, first time,
with no delete/re-upload. Documents: CLIENT -> DOCUMENT -> ACTION through
browser channels, with status rules enforced server-side.
"""

from app.models import db
from app.models.crm import Client, Contact, Followup, Lead
from app.models.document import Document
from app.models.operations import ActivityEvent
from app.models.project import Project, ProjectCategory, ProjectMedia
from tests.conftest import login, post
from tests.test_actions import make_ready_doc
from tests.test_operations import authed, make_client, make_project, opost


def make_showcase_project(slug="showcase", title="Showcase"):
    category = ProjectCategory.query.filter_by(slug="built").first()
    if category is None:
        category = ProjectCategory(name="Built", slug="built")
        db.session.add(category)
        db.session.flush()
    project = Project(title=title, slug=slug, status="COMPLETED",
                      category_id=category.id)
    db.session.add(project)
    db.session.commit()
    return project


def add_media(client, token, project, **fields):
    data = {"media_type": "image",
            "file_path": "https://example.com/shot.png",
            "alt_text": "", "caption": "", "display_order": "0"}
    data.update(fields)
    return opost(client, f"/admin/projects/{project.id}/media", token, data)


def make_full_contact(phone="+91 90000 00011", email="full@example.com"):
    contact = Contact(name="Full Client", email=email, phone=phone,
                      company="Full Co", message="Hi")
    db.session.add(contact)
    db.session.flush()
    db.session.add(Lead(contact_id=contact.id, status="LEAD"))
    client = Client(contact_id=contact.id, company="Full Co")
    db.session.add(client)
    db.session.commit()
    return client


# ------------------------------------------------------------------ media

def test_create_upload_save_renders_first_time(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    response = add_media(client, token, project,
                         file_path="https://example.com/first.png")
    assert response.status_code == 302
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert '<img src="https://example.com/first.png"' in html


def test_remote_image_url_correct(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    add_media(client, token, project, alt_text="Hero shot",
              file_path="https://cdn.example.com/hero.jpg")
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert 'src="https://cdn.example.com/hero.jpg"' in html
    assert 'alt="Hero shot"' in html


def test_local_static_path_renders(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    add_media(client, token, project, file_path="images/project/local.png")
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert '<img src="/static/images/project/local.png"' in html


def test_second_media_both_render(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    add_media(client, token, project, file_path="https://example.com/a.png")
    add_media(client, token, project, file_path="images/project/b.png")
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert 'src="https://example.com/a.png"' in html
    assert 'src="/static/images/project/b.png"' in html


def test_uppercase_media_type_still_renders(client, admin_user):
    """Legacy rows stored with non-lowercase types must still render."""
    project = make_showcase_project()
    db.session.add(ProjectMedia(project_id=project.id, media_type="Image",
                                file_path="https://example.com/legacy.png"))
    db.session.commit()
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert '<img src="https://example.com/legacy.png"' in html


def test_video_renders_video_element(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    add_media(client, token, project, media_type="video",
              file_path="uploads/media/demo.mp4")
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert "<video" in html
    assert 'src="/static/uploads/media/demo.mp4"' in html


def test_project_without_media_renders(client, admin_user):
    project = make_showcase_project()
    response = client.get(f"/work/{project.slug}")
    assert response.status_code == 200
    assert "Visual evidence" not in response.get_data(as_text=True)


def test_missing_media_does_not_break_page(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    add_media(client, token, project, alt_text="Gone",
              file_path="uploads/media/missing.png")
    response = client.get(f"/work/{project.slug}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'src="/static/uploads/media/missing.png"' in html
    assert 'alt="Gone"' in html  # graceful degradation text survives


def test_unsupported_media_falls_back_to_record(client, admin_user):
    project = make_showcase_project()
    db.session.add(ProjectMedia(project_id=project.id, media_type="audio",
                                file_path="audio/note.mp3"))
    db.session.commit()
    response = client.get(f"/work/{project.slug}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<figure" not in html
    assert "<video" not in html
    assert "audio/note.mp3" in html


def test_invalid_media_type_rejected(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    response = add_media(client, token, project, media_type="audio",
                         file_path="audio/note.mp3")
    assert response.status_code == 302
    assert ProjectMedia.query.count() == 0


def test_media_edit_reflects_on_public_page(client, admin_user):
    project = make_showcase_project()
    token = authed(client, admin_user)
    add_media(client, token, project, file_path="https://example.com/old.png")
    media = ProjectMedia.query.one()
    opost(client, f"/admin/projects/media/{media.id}/edit", token,
          {"media_type": "image", "file_path": "https://example.com/new.png",
           "alt_text": "", "caption": "", "display_order": "0"})
    html = client.get(f"/work/{project.slug}").get_data(as_text=True)
    assert "https://example.com/new.png" in html
    assert "https://example.com/old.png" not in html


# ---------------------------------------------------------- document links

def document_form(client_id="", project_id=""):
    return {
        "title": "Website Proposal",
        "category": "CLIENT_PROJECT",
        "doc_type": "Project Proposal",
        "description": "Proposal.",
        "status": "DRAFT",
        "url_or_path": "https://docs.example.com/p1",
        "client_id": client_id,
        "project_id": project_id,
    }


def test_document_links_to_existing_client_and_project(client, admin_user):
    owner = make_client()
    work = make_project(owner)
    before = Client.query.count()
    token = authed(client, admin_user)
    response = opost(client, "/admin/documents/new", token,
                     document_form(client_id=str(owner.id),
                                   project_id=str(work.id)))
    assert response.status_code == 302
    document = Document.query.one()
    assert document.client_id == owner.id
    assert document.project_id == work.id
    assert Client.query.count() == before  # no duplicate client created


def test_document_link_rejects_foreign_project(client, admin_user):
    owner = make_client()
    other = make_client("Other")
    work = make_project(other)
    token = authed(client, admin_user)
    response = opost(client, "/admin/documents/new", token,
                     document_form(client_id=str(owner.id),
                                   project_id=str(work.id)))
    assert response.status_code == 200
    assert "does not belong" in response.get_data(as_text=True)
    assert Document.query.count() == 0


def test_document_link_rejects_unknown_client(client, admin_user):
    token = authed(client, admin_user)
    response = opost(client, "/admin/documents/new", token,
                     document_form(client_id="9999"))
    assert response.status_code == 200
    assert Document.query.count() == 0


# ------------------------------------------------------- document actions

def test_ready_document_shows_all_channels(client, admin_user):
    owner = make_full_contact()
    document = make_ready_doc(owner, doc_type="Project Proposal",
                              title="Proposal", number="PR-101")
    document.category = "CLIENT_PROJECT"
    db.session.commit()
    login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Send via" in html
    assert "WhatsApp" in html
    assert "Email" in html
    assert "SMS" in html
    assert 'href="tel:+91 90000 00011"' in html
    assert f"document_id={document.id}" in html


def test_client_without_phone_hides_phone_channels(client, admin_user):
    owner = make_client()  # contact has email, no phone
    document = make_ready_doc(owner)
    login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Send via" in html
    assert "channel=EMAIL" in html
    assert "channel=WHATSAPP" not in html
    assert "channel=SMS" not in html
    assert "tel:" not in html


def test_client_without_any_contact_method(client, admin_user):
    contact = Contact(name="Silent", email="", phone=None, message="Hi")
    db.session.add(contact)
    db.session.flush()
    db.session.add(Lead(contact_id=contact.id, status="LEAD"))
    owner = Client(contact_id=contact.id)
    db.session.add(owner)
    db.session.commit()
    document = make_ready_doc(owner)
    login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "No communication method available for this client." in html


def test_draft_document_cannot_send(client, admin_user):
    owner = make_full_contact()
    document = make_ready_doc(owner, status="DRAFT", number="QT-201")
    _, token = login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Send via" not in html
    assert "edit before sending" in html.lower()
    response = opost(
        client, f"/admin/crm/client/{owner.id}/actions/prepare", token,
        {"purpose": "QUOTATION", "channel": "EMAIL", "message": "Hi",
         "scheduled_at": "", "document_id": str(document.id),
         "project_id": "", "invoice_id": ""})
    assert response.status_code == 200
    assert Followup.query.count() == 0


def test_archived_document_view_only(client, admin_user):
    owner = make_full_contact()
    document = make_ready_doc(owner, status="ARCHIVED", number="QT-202")
    _, token = login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Send via" not in html
    assert "Archived — view only" in html
    response = opost(
        client, f"/admin/crm/client/{owner.id}/actions/prepare", token,
        {"purpose": "QUOTATION", "channel": "EMAIL", "message": "Hi",
         "scheduled_at": "", "document_id": str(document.id),
         "project_id": "", "invoice_id": ""})
    assert Followup.query.count() == 0


def test_document_without_client_prompts_link(client, admin_user):
    document = Document(title="Orphan Quote", category="PRICING_APPROVAL",
                        doc_type="Quotation", status="READY")
    db.session.add(document)
    db.session.commit()
    login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "No client linked" in html
    assert "Link client" in html
    assert "Send via" not in html


def test_internal_document_type_cannot_be_shared(client, admin_user):
    owner = make_full_contact()
    document = Document(title="Call notes", category="PROJECT_EXECUTION",
                        doc_type="Meeting / Call Notes", status="READY",
                        client_id=owner.id)
    db.session.add(document)
    db.session.commit()
    _, token = login(client)
    html = client.get(
        f"/admin/documents/{document.id}").get_data(as_text=True)
    assert "Send via" not in html
    assert "admin-only" in html
    response = opost(
        client, f"/admin/crm/client/{owner.id}/actions/prepare", token,
        {"purpose": "GENERAL", "channel": "EMAIL", "message": "Hi",
         "scheduled_at": "", "document_id": str(document.id),
         "project_id": "", "invoice_id": ""})
    assert response.status_code == 200
    assert "internal" in response.get_data(as_text=True).lower()
    assert Followup.query.count() == 0


def test_vault_list_shows_client_and_send(client, admin_user):
    owner = make_client()
    make_ready_doc(owner)
    login(client)
    html = client.get("/admin/documents").get_data(as_text=True)
    assert "Acme Owner" in html
    assert "Send" in html


def test_vault_list_hides_send_for_internal_type(client, admin_user):
    owner = make_client()
    document = Document(title="Call notes", category="PROJECT_EXECUTION",
                        doc_type="Meeting / Call Notes", status="READY",
                        client_id=owner.id)
    db.session.add(document)
    db.session.commit()
    login(client)
    html = client.get("/admin/documents").get_data(as_text=True)
    assert "Send" not in html


def test_client_workspace_document_has_send_actions(client, admin_user):
    owner = make_full_contact()
    work = make_project(owner)
    document = make_ready_doc(owner, number="QT-301")
    document.project_id = work.id
    db.session.commit()
    login(client)
    html = client.get(
        f"/admin/crm/clients/{owner.id}").get_data(as_text=True)
    assert "Send via" in html
    assert "Open" in html
    assert "Edit" in html
    assert f"document_id={document.id}" in html


def test_compose_warns_on_forced_draft_document(client, admin_user):
    owner = make_client()
    document = make_ready_doc(owner, status="DRAFT", number="QT-302")
    login(client)
    html = client.get(
        f"/admin/crm/client/{owner.id}/actions/compose"
        f"?document_id={document.id}").get_data(as_text=True)
    assert "only READY documents" in html


def test_prepare_logs_prepared_never_sent(client, admin_user):
    owner = make_full_contact()
    document = make_ready_doc(owner, number="QT-303")
    token = authed(client, admin_user)
    response = opost(
        client, f"/admin/crm/client/{owner.id}/actions/prepare", token,
        {"purpose": "QUOTATION", "channel": "EMAIL",
         "message": "Please review.", "scheduled_at": "",
         "document_id": str(document.id), "project_id": "",
         "invoice_id": ""})
    assert response.status_code == 302
    types = {e.event_type for e in ActivityEvent.query.all()}
    assert "DOCUMENT_PREPARED" in types
    assert not {t for t in types if "SENT" in t or "DELIVERED" in t}
    followup = Followup.query.one()
    html = client.get(
        f"/admin/actions/confirm/{followup.id}").get_data(as_text=True)
    assert "PREPARED" in html
    assert "MESSAGE SENT" not in html


def test_prepare_requires_csrf(client, admin_user):
    owner = make_full_contact()
    make_ready_doc(owner)
    login(client)
    response = client.post(
        f"/admin/crm/client/{owner.id}/actions/prepare",
        data={"purpose": "GENERAL", "channel": "EMAIL", "message": "Hi"})
    assert response.status_code == 400
    assert Followup.query.count() == 0


def test_cross_client_document_forgery_dropped(client, admin_user):
    owner = make_full_contact()
    other = make_client("Other")
    foreign = make_ready_doc(other, number="QT-304")
    token = authed(client, admin_user)
    response = opost(
        client, f"/admin/crm/client/{owner.id}/actions/prepare", token,
        {"purpose": "GENERAL", "channel": "EMAIL", "message": "Forged",
         "scheduled_at": "", "document_id": str(foreign.id),
         "project_id": "", "invoice_id": ""})
    assert response.status_code == 302
    assert Followup.query.one().document_id is None


def test_message_variables_resolve_without_leaks():
    from app.services.messages import build_context, render_message

    ctx = build_context(client_name="ABC Business",
                        project_name="Business Website",
                        document_name="Quotation",
                        document_number="QT-001",
                        document_url="https://docs.example.com/qt-001")
    text = render_message("QUOTATION", ctx)
    assert "ABC Business" in text
    assert "QT-001" in text
    assert "{{" not in text and "}}" not in text
    empty = render_message("QUOTATION", {})
    assert "{{" not in empty and "}}" not in empty


def test_whatsapp_message_mentions_document_link(client, admin_user):
    owner = make_full_contact()
    document = make_ready_doc(owner, number="QT-305")
    document.url_or_path = "https://docs.example.com/qt-305"
    db.session.commit()
    token = authed(client, admin_user)
    opost(
        client, f"/admin/crm/client/{owner.id}/actions/prepare", token,
        {"purpose": "QUOTATION", "channel": "WHATSAPP",
         "message": "Please review https://docs.example.com/qt-305",
         "scheduled_at": "", "document_id": str(document.id),
         "project_id": "", "invoice_id": ""})
    followup = Followup.query.one()
    html = client.get(
        f"/admin/actions/confirm/{followup.id}").get_data(as_text=True)
    assert "wa.me/919000000011" in html
    assert "docs.example.com/qt-305" in html
    assert "Open WhatsApp" in html
