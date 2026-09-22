"""Visual/UX tests: R&D route, nav, homepage sections, design system."""

import re

from app.models import db
from app.models.project import Project, ProjectMedia
from app.seed import seed_portfolio
from tests.conftest import login


def test_rnd_page_renders_rd_projects(client):
    seed_portfolio()
    html = client.get("/r-and-d").get_data(as_text=True)
    assert client.get("/r-and-d").status_code == 200
    assert "CLH.WP" in html
    assert "Autonomous Economic Agent" in html
    # Built projects must not appear in the R&D listing itself
    # (the footer verified-links block is site-wide and exempt).
    main = html.split("<footer")[0]
    assert "Estora" not in main
    assert "Umama Motors" not in main


def test_rnd_page_404_without_category(client):
    assert client.get("/r-and-d").status_code == 404


def test_nav_exposes_all_sections_with_active_state(client):
    html = client.get("/").get_data(as_text=True)
    for href in ["/", "/work", "/r-and-d", "/process", "/context",
                 "/learning", "/contact"]:
        assert f'href="{href}"' in html
    assert "R&amp;D" in html
    assert 'aria-current="page"' in html
    assert "Skip to content" in html


def test_homepage_surfaces_seeded_work_learning_commercial(client):
    seed_portfolio()
    html = client.get("/").get_data(as_text=True)
    assert "Estora" in html
    assert "Umama Motors" in html
    assert "CLH.WP" in html
    assert "Web application architecture" in html
    assert "Custom websites and lightweight business systems" in html
    assert "Start a project enquiry" in html
    assert "I build software to understand it." in html


def test_work_page_groups_built_and_rd_with_legend(client):
    seed_portfolio()
    html = client.get("/work").get_data(as_text=True)
    assert "Built" in html
    assert "R&amp;D" in html
    assert "Status key" in html


def test_detail_status_proof_banner_and_chips(client):
    seed_portfolio()
    estora = client.get("/work/estora").get_data(as_text=True)
    assert "status-banner" in estora
    assert "maturity" in estora
    assert "evidence on record" in estora
    assert "chip-completed" in estora
    clh = client.get("/work/clh-wp").get_data(as_text=True)
    assert "chip-beta" in clh


def test_design_system_css_serves(client):
    main = client.get("/static/css/main.css")
    assert main.status_code == 200
    css = main.get_data(as_text=True)
    assert ":root" in css
    assert "--signal" in css
    assert "prefers-reduced-motion" in css
    assert "skip-link" in css
    admin = client.get("/static/css/admin.css")
    assert admin.status_code == 200
    assert ".pill" in admin.get_data(as_text=True)


def test_admin_lists_use_pills_after_login(client, admin_user):
    seed_portfolio()
    login(client)
    projects_html = client.get("/admin/projects").get_data(as_text=True)
    assert "pill-" in projects_html
    assert "table-wrap" in projects_html


def test_estora_live_demo_prominent_no_invented_source(client):
    seed_portfolio()
    html = client.get("/work/estora").get_data(as_text=True)
    assert "access-row" in html
    assert "https://estora-2y3m.onrender.com/" in html
    assert "Live Demo" in html
    # No source-code URL invented for Estora (footer block exempt).
    main = html.split("<footer")[0]
    assert "github" not in main.lower()


def test_umama_verified_live_demo_and_source(client):
    seed_portfolio()
    html = client.get("/work/umama-motors").get_data(as_text=True)
    assert "https://github.com/Hanzalaq/umama-motors" in html
    # User-verified live URL now seeded: both actions prominent.
    assert "https://umama-motors.onrender.com/" in html
    assert "Open live demo" in html
    assert "View source" in html


def test_elsewhere_block_lists_verified_links(client):
    seed_portfolio()
    html = client.get("/").get_data(as_text=True)
    assert "Elsewhere" in html
    assert "https://estora-2y3m.onrender.com/" in html
    assert "https://github.com/Hanzalaq/umama-motors" in html


def test_elsewhere_absent_gracefully_without_links(client):
    html = client.get("/").get_data(as_text=True)
    assert client.get("/").status_code == 200
    # The label stays; the link list itself must not render.
    assert 'class="elsewhere"' not in html


def test_remote_media_renders_img_with_alt(client):
    seed_portfolio()
    project = Project.query.filter_by(slug="estora").one()
    db.session.add(ProjectMedia(
        project_id=project.id, media_type="image",
        file_path="https://example.com/shot.png",
        alt_text="Estora dashboard view", caption="Admin view",
        display_order=0, is_primary=True,
    ))
    db.session.commit()
    html = client.get("/work/estora").get_data(as_text=True)
    assert "<img" in html
    assert 'alt="Estora dashboard view"' in html
    assert "Visual evidence" in html


def test_local_media_renders_metadata_without_img(client):
    seed_portfolio()
    project = Project.query.filter_by(slug="estora").one()
    db.session.add(ProjectMedia(
        project_id=project.id, media_type="image",
        file_path="images/local-shot.png", alt_text="Local shot",
        display_order=0,
    ))
    db.session.commit()
    html = client.get("/work/estora").get_data(as_text=True)
    # A local path renders as metadata, never as an evidence image.
    assert "images/local-shot.png" in html
    assert '<img src="images/local-shot.png"' not in html
    # Seeded remote evidence (real live-site assets) still renders.
    assert '<figure class="evidence-frame">' in html


def test_rd_cards_show_question_and_next(client):
    seed_portfolio()
    html = client.get("/r-and-d").get_data(as_text=True)
    assert "Question:" in html
    assert "Next:" in html
    assert "file-rd" in html


def test_leadership_experience_renders(client):
    seed_portfolio()
    context = client.get("/context").get_data(as_text=True)
    assert "AVYGEN AI" in context
    assert "Technical &amp; AI Lead" in context
    home = client.get("/").get_data(as_text=True)
    assert "AVYGEN AI" in home
    assert "Where the work comes from" in home


def test_enquiry_form_fields_and_prompt(client):
    html = client.get("/contact").get_data(as_text=True)
    assert "Start a project" in html
    assert 'name="service_interest"' in html
    assert "What are you trying to build" in html
    assert "Send project enquiry" in html
    assert 'name="csrf_token"' in html
    assert 'name="website"' in html


def test_homepage_hero_identity_actions_sidebar(client):
    seed_portfolio()
    html = client.get("/").get_data(as_text=True)
    assert "PORTFOLIO / HZ" in html
    assert "Building in public" in html
    assert "View work" in html
    assert "R&amp;D lab" in html
    assert "Work with me" in html
    assert "Location" in html
    assert "Focus" in html
    assert "Try this" in html
    assert "Same curiosity" in html


def test_homepage_selected_work_row(client):
    seed_portfolio()
    html = client.get("/").get_data(as_text=True)
    assert "Selected work" in html
    assert "Business Systems" in html
    assert "feature-number" in html


def test_homepage_lower_strip_links(client):
    html = client.get("/").get_data(as_text=True)
    assert "cards-triple" in html
    for href in ["/process", "/context", "/learning"]:
        assert f'href="{href}"' in html


def test_game_js_serves(client):
    response = client.get("/static/js/build-loop.js")
    assert response.status_code == 200
    assert "data-game" in response.get_data(as_text=True)


def test_hero_portrait_present(client):
    html = client.get("/").get_data(as_text=True)
    assert 'src="/static/images/hanzala-portrait.png"' in html
    assert 'alt="Portrait of Hanzala"' in html
    assert "portrait-tag" in html
    assert "Same curiosity" in html


def test_avatar_assets_serve(client):
    for asset in ("hanzala-portrait.png", "hanzala-avatar.png"):
        response = client.get(f"/static/images/{asset}")
        assert response.status_code == 200, asset
        assert response.content_type.startswith("image/png")


def test_game_modal_markup(client):
    html = client.get("/").get_data(as_text=True)
    assert "TRY THIS" in html or "Try this" in html
    assert "data-game-open" in html
    assert 'role="dialog"' in html
    assert "data-game-targets" in html
    assert "data-game-replay" in html
    assert "data-game-close" in html
    assert "You found the loop" in html
    # Robot token, not a human photo, inside the modal.
    assert "bot-token" in html


def test_game_buttons_are_real_buttons(client):
    html = client.get("/").get_data(as_text=True)
    assert '<button type="button" data-game-play>Play</button>' in html
    assert "PLAY AGAIN" in html.upper()


def test_final_avatar_assets(client):
    for asset, min_bytes in (("hanzala-portrait.png", 100_000),
                             ("hanzala-avatar.png", 50_000)):
        response = client.get(f"/static/images/{asset}")
        assert response.status_code == 200, asset
        assert response.content_type.startswith("image/png")
        assert len(response.get_data()) > min_bytes, asset


def test_hero_header_game_use_final_avatar(client):
    html = client.get("/").get_data(as_text=True)
    assert 'src="/static/images/hanzala-portrait.png"' in html
    assert 'width="620" height="840"' in html
    assert 'class="brand-avatar"' in html
    assert html.count("/static/images/hanzala-avatar.png") >= 1


def test_game_uses_robot_not_human_photo(client):
    html = client.get("/").get_data(as_text=True)
    modal = html.split('<div class="game-modal"')[1].split("</main>")[0]
    assert "hanzala-avatar" not in modal
    assert "hanzala-portrait" not in modal
    assert "<svg" in modal
    assert "Build bot" in modal


def test_rd_thumbnails_readable(client):
    seed_portfolio()
    html = client.get("/r-and-d").get_data(as_text=True)
    assert "card-thumb" in html
    assert "Lead discovery + Qualification" in html
    assert "Decision systems + Risk" in html
    assert "R&amp;D / BETA" in html
    assert "R&amp;D / PLANNING" in html
    assert "file-rd" in html
    css = client.get("/static/css/main.css").get_data(as_text=True)
    # Thumb title is near-black ink on a paper surface: never white-on-white.
    title_block = css.split(".card-thumb-title")[1].split("}")[0]
    assert "color: var(--text)" in title_block
    assert ".card-thumb-status" in css


def test_social_links_exact_and_nothing_invented(client):
    html = client.get("/").get_data(as_text=True)
    for url in ("https://github.com/Hanzalaq/",
                "https://www.instagram.com/hsq.dev/",
                "https://www.instagram.com/qhanzala25/",
                "mailto:hsqfreelances@gmail.com",
                "https://wa.me/917798727978"):
        assert url in html, url
    lowered = html.lower()
    for invented in ("linkedin", "twitter", "facebook", "discord",
                     "avygen.com", "x.com/"):
        assert invented not in lowered, invented
    contact = client.get("/contact").get_data(as_text=True)
    assert "https://wa.me/917798727978" in contact
    assert "mailto:hsqfreelances@gmail.com" in contact


def test_avygen_plain_text_no_link(client):
    seed_portfolio()
    for page in ("/", "/context"):
        html = client.get(page).get_data(as_text=True)
        assert "AVYGEN AI" in html
    assert "avygen" not in client.get("/context").get_data(as_text=True).lower().replace(
        "avygen ai", "")


def test_umama_live_url_seeded(client):
    seed_portfolio()
    assert "umama-motors.onrender.com" in client.get("/work/umama-motors").get_data(as_text=True)
    assert "umama-motors.onrender.com" in client.get("/").get_data(as_text=True)


def test_work_pages_use_editorial_files(client):
    seed_portfolio()
    for url in ("/work", "/r-and-d"):
        html = client.get(url).get_data(as_text=True)
        assert "file-title" in html
        assert "file-proof" in html
        assert "Case file" in html
    work = client.get("/work").get_data(as_text=True)
    assert "Open live demo" in work
    assert "View source" in work


def test_avygen_responsibilities_render(client):
    seed_portfolio()
    html = client.get("/context").get_data(as_text=True)
    assert "Technical &amp; AI Lead" in html
    assert "Client onboarding" in html or "client onboarding" in html


def test_mobile_css_guards(client):
    css = client.get("/static/css/main.css").get_data(as_text=True)
    assert "@media (max-width: 22.5rem)" in css
    assert "min-width: 0" in css
    assert ".game-modal" in css
    assert "90dvh" in css


def test_admin_nav_core_links(client, admin_user):
    login(client)
    html = client.get("/admin/dashboard").get_data(as_text=True)
    for href in ("/admin/dashboard", "/admin/projects", "/admin/crm"):
        assert f'href="{href}"' in html
    assert "Log out" in html


def test_identity_palette_and_grid(client):
    css = client.get("/static/css/main.css").get_data(as_text=True)
    for token in ("#F1EBDD", "#11100D", "#292722", "#D5CEC1", "#F0442E",
                  "#3047C7", "#B7D52B"):
        assert token in css, token
    assert "48px 48px" in css
    assert "--tech" in css
    assert "--lime" in css


def test_external_links_open_new_tab(client):
    seed_portfolio()
    for url in ("/", "/work", "/work/estora", "/work/umama-motors",
                "/contact", "/r-and-d"):
        html = client.get(url).get_data(as_text=True)
        for match in re.finditer(r'<a\s[^>]*href="(https?://|mailto:)[^"]*"[^>]*>', html):
            tag = match.group(0)
            if "mailto:" in tag:
                continue
            assert 'target="_blank"' in tag, (url, tag)
            assert 'rel="noopener noreferrer"' in tag, (url, tag)


def test_internal_links_stay_same_tab(client):
    seed_portfolio()
    html = client.get("/").get_data(as_text=True)
    for match in re.finditer(r'<a\s[^>]*href="(/[^"]*)"', html):
        assert 'target="_blank"' not in match.group(0), match.group(1)


def test_proof_slab_copy(client):
    seed_portfolio()
    html = client.get("/").get_data(as_text=True)
    assert "Live systems. Real links. No claims without proof." in html
    assert "panel-dark" in html


def test_section_headers_have_rules(client):
    css = client.get("/static/css/main.css").get_data(as_text=True)
    label_block = css.split(".section-label {")[1].split("}")[0]
    assert "border-bottom" in label_block


def test_avygen_responsibilities_render(client):
    seed_portfolio()
    html = client.get("/context").get_data(as_text=True)
    assert "Technical &amp; AI Lead" in html
    assert "Client onboarding" in html or "client onboarding" in html
