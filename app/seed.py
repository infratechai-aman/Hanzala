"""Repeatable portfolio content seed.

`flask seed-portfolio` inserts or updates the real portfolio dataset
(categories, projects, links, experiences, learning items) using stable
slugs/titles as identity, so it is safe to run repeatedly: existing rows
are updated in place, never duplicated.

Deliberately untouched: admin users, all CRM tables, project media, and
any record the seed data does not describe. Nothing is ever deleted.
"""

from app.models import db
from app.models.experience import Experience
from app.models.learning import LearningItem
from app.models.media_vault import PortfolioMedia
from app.models.project import (
    Project,
    ProjectCategory,
    ProjectLink,
    ProjectMedia,
)

# Real evidence media, discovered from the live deployed projects
# (inspected 2026-09-12). Every URL below was observed in the actual
# page HTML of the live site noted in `caption`; nothing is invented,
# AI-generated, or substituted stock. Remote URLs render as evidence
# images through the existing public case-study template.
PROJECT_MEDIA = [
    {
        "project_slug": "estora",
        "media_type": "image",
        "file_path": "https://lh3.googleusercontent.com/aida-public/AB6AXuCO9R6mYK4I_XNK8s-w6hyHU1YOuhpm0n8lX20shTtxY1_6KB6YV-6V3kjtjfweSL5rz2EfobaoqMGoj1iwlAykcOmS4pBeuhnxLdYHRwNZqw8k3uGxhi4hNxjMwyWauhbn9Fc1FMP84Da6My4eJrFtJ23ufqXT8CEf7fBm6gooRtGjOBJN5LzdaThHCtJ5sCoodz05_C0UA2K7pL28ed9x0QO7mVugi1890mSRuvm2JevumAdU2vl2",
        "alt_text": "KIN Properties logo as deployed on the live website",
        "caption": "Project logo as deployed (live site brands as KIN Properties).",
        "display_order": 0,
        "is_primary": True,
    },
    {
        "project_slug": "estora",
        "media_type": "image",
        "file_path": "https://lh3.googleusercontent.com/aida-public/AB6AXuAHaKBk0T_zIfVKIQCSSgN3aGAmZI0Jw-oZ_RVqM-Rd0oQBgc-zSePEOWY6hemIkj6OVMqZJF2lgYFJZZYQYlx1_xXYJ4wJoBre6a5ETIwRFE_0iFNDQhODTfPIakjThMurhQ2eik93SKOFxXS-pKJASiwhVfx6_CXLFSSLKAJrtNc45omesOL-z0-5jdCTAW9T6aVHPXJgYjqPj71apEfgKAxI9glsnPXCopy_7Sz7PzVEZQLrMTt",
        "alt_text": "Penthouse on the Lake, Kalyani Nagar listing imagery",
        "caption": "Featured listing imagery as deployed on the live website.",
        "display_order": 1,
        "is_primary": False,
    },
    {
        "project_slug": "estora",
        "media_type": "image",
        "file_path": "https://lh3.googleusercontent.com/aida-public/AB6AXuDr45Db2sfdszphayx_HiRtc-zswP9rqgFp8keFial-ll0_NNaLnkMzGtBGhUKrCNRZZCekjEow7fETmQruWldGXyX7ijSYp4o2JLqdHp3Ch5jRpH1KTa_ZJ5GdvSyRHpm2gkwjm-mQoUlOhTExYILnFOdfzWIv15xudyESfbbyW309YmCi3T1J4tm1YWG2WGV-qL50oX_hZWCr1_CJPUupHzfKRsrfvysVChodVurYXzt4c4Gu1fK-",
        "alt_text": "Sky Penthouse, Koregaon Park listing imagery",
        "caption": "Featured listing imagery as deployed on the live website.",
        "display_order": 2,
        "is_primary": False,
    },
    {
        "project_slug": "umama-motors",
        "media_type": "image",
        "file_path": "https://umama-motors.onrender.com/static/logo.svg",
        "alt_text": "Umama Motors logo from the live website",
        "caption": "Project logo served by the live website itself.",
        "display_order": 0,
        "is_primary": True,
    },
    {
        "project_slug": "umama-motors",
        "media_type": "image",
        "file_path": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/BMW_M3_Competition_%28G80%29_IMG_4041.jpg/330px-BMW_M3_Competition_%28G80%29_IMG_4041.jpg",
        "alt_text": "BMW 3 Series M340i inventory imagery",
        "caption": "Inventory imagery as shown on the live website (Wikimedia Commons source, as deployed).",
        "display_order": 1,
        "is_primary": False,
    },
    {
        "project_slug": "umama-motors",
        "media_type": "image",
        "file_path": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1d/Audi_A3_8Y_Sedan_IMG_5936.jpg/330px-Audi_A3_8Y_Sedan_IMG_5936.jpg",
        "alt_text": "Audi A3 Technology inventory imagery",
        "caption": "Inventory imagery as shown on the live website (Wikimedia Commons source, as deployed).",
        "display_order": 2,
        "is_primary": False,
    },
]

CATEGORIES = [
    {
        "name": "Built",
        "slug": "built",
        "description": "Finished systems built end to end: designed, implemented, and documented.",
    },
    {
        "name": "R&D",
        "slug": "r-and-d",
        "description": "Experiments and research directions. Unfinished by design.",
    },
]

PROJECTS = [
    {
        "title": "Estora",
        "slug": "estora",
        "category_slug": "built",
        "status": "COMPLETED",
        "role": "Developer / Builder",
        "short_description": "A real-estate property management and presentation system.",
        "description": (
            "Estora is a real-estate property management and presentation system: "
            "a public-facing property experience connected to an administrative "
            "backend for managing property information."
        ),
        "why": (
            "Built around the need to manage property information, present listings, "
            "and provide an operational backend rather than relying on disconnected "
            "manual workflows."
        ),
        "problem": (
            "Real-estate information and operational work can become fragmented across "
            "spreadsheets, messages, files, and manual updates."
        ),
        "system_description": (
            "Public-facing property experience connected to an administrative backend "
            "for managing property information. The deployed site publicly brands "
            "itself as KIN Properties, a residential and commercial brokerage for Pune."
        ),
        "technical_details": "Python / Flask / SQL / Jinja / HTML / CSS / JavaScript",
        "decisions": (
            "Server-rendered architecture. Database-backed content. Private "
            "administrative interface. Separation between public presentation and "
            "internal management. Reusable CRUD patterns."
        ),
        "result": "A functioning real-estate software system and working portfolio project.",
        "proof": "LIVE DEMO / SOURCE CODE / ADMIN SYSTEM",
        "limitations": (
            "No commercial traction is claimed: no revenue, customers, traffic, "
            "or production scale. Only what the implementation demonstrates."
        ),
        "next_steps": (
            "Continue improving the system architecture and use the lessons from it "
            "in later business systems."
        ),
        "is_featured": True,
        "display_order": 1,
        "links": [
            {
                "label": "Live Demo",
                "url": "https://estora-2y3m.onrender.com/",
                "link_type": "demo",
                "display_order": 0,
            },
        ],
    },
    {
        "title": "Umama Motors",
        "slug": "umama-motors",
        "category_slug": "built",
        "status": "COMPLETED",
        "role": "Developer / Builder",
        "short_description": (
            "A full-stack car dealership platform with a database-driven public "
            "showroom and private administration system."
        ),
        "description": (
            "A full-stack car dealership platform: vehicle inventory, filtering, "
            "vehicle detail pages, and an enquiry flow on the public side; vehicle "
            "CRUD, image/media handling, lead/enquiry management, and administrative "
            "settings on the private side."
        ),
        "why": "To apply the same underlying software architecture to a different business domain.",
        "problem": (
            "A dealership needs more than a static website: inventory needs to be "
            "managed, vehicles need individual pages, and enquiries need to reach "
            "an operational backend."
        ),
        "system_description": (
            "Public: vehicle inventory, filtering, vehicle detail pages, enquiry flow. "
            "Private: vehicle CRUD, image/media handling, lead/enquiry management, "
            "administrative settings."
        ),
        "technical_details": (
            "Flask 3.1 / SQLAlchemy / SQLite / PostgreSQL-MySQL through DATABASE_URL / "
            "Jinja / HTML-CSS-JavaScript / Werkzeug password hashing / CSRF protection / "
            "Gunicorn"
        ),
        "decisions": (
            "Database-driven inventory. Public/private separation. Reusable CRUD "
            "architecture. Business-domain modeling rather than static pages."
        ),
        "result": (
            "A functioning dealership web application demonstrating that the "
            "architecture transfers between business domains."
        ),
        "proof": "SOURCE CODE / LIVE DEMO / ADMIN SYSTEM",
        "limitations": (
            "No dealership revenue, production scale, or customer volume is claimed. "
            "Only what the implementation demonstrates."
        ),
        "next_steps": "Use the same principles for increasingly general business systems.",
        "is_featured": True,
        "display_order": 2,
        "links": [
            {
                "label": "Live Demo",
                "url": "https://umama-motors.onrender.com/",
                "link_type": "demo",
                "display_order": 0,
            },
            {
                "label": "GitHub",
                "url": "https://github.com/Hanzalaq/umama-motors",
                "link_type": "code",
                "display_order": 1,
            },
        ],
    },
    {
        "title": "Business Systems / Small SaaS",
        "slug": "business-systems",
        "category_slug": "built",
        "status": "COMPLETED",
        "role": "Developer / Builder",
        "short_description": (
            "Small operational systems and experiments built from real business "
            "workflow problems."
        ),
        "description": (
            "A collection of small operational systems and experiments built from real "
            "business workflow problems. The recurring problem was not simply that a "
            "website was needed: business information, leads, tasks, and operations "
            "become difficult to manage when everything lives in disconnected tools."
        ),
        "why": (
            "Real-estate operational experience exposed problems around spreadsheets, "
            "data handling, inconsistent information, and fragile manual workflows. "
            "Each prototype was an attempt to digitize one such workflow."
        ),
        "problem": (
            "Business information scattered across spreadsheets and messages leads to "
            "inconsistent data and fragile manual processes."
        ),
        "system_description": (
            "Prototype operational applications, including White Chicken: built from "
            "client/business requirements as a prototype operational application. The "
            "engagement did not become a completed client handoff, and it is not "
            "presented as a deployed commercial product."
        ),
        "technical_details": (
            "CRUD / data modeling / administrative interfaces / workflow design / "
            "lead handling / business process digitization"
        ),
        "decisions": (
            "Model the business process first, then build the smallest system that "
            "holds the data reliably. Real operational exposure — including work "
            "around the Vespera context — showed why business systems need reliable "
            "data structures and workflows."
        ),
        "result": (
            "This work established the foundation for later CRM, lead qualification, "
            "and business-system projects."
        ),
        "proof": "DOCUMENTATION / PROTOTYPE / REAL-WORLD EXPERIENCE",
        "limitations": "Not every prototype became a production deployment.",
        "next_steps": "Generalize these patterns into reusable lightweight business systems.",
        "is_featured": False,
        "display_order": 4,
        "links": [],
    },
    {
        "title": "CLH.WP",
        "slug": "clh-wp",
        "category_slug": "r-and-d",
        "status": "BETA",
        "role": "Developer / System Builder",
        "short_description": (
            "A system for discovering and qualifying business opportunities from "
            "multiple sources. In active testing."
        ),
        "description": (
            "A system for discovering and qualifying business opportunities from "
            "multiple sources. Core concept: DISCOVER, COLLECT EVIDENCE, QUALIFY, "
            "PRIORITIZE."
        ),
        "why": "Manual lead hunting is repetitive, inconsistent, and difficult to scale.",
        "problem": (
            "Finding potential businesses is only the first step. The system needs to "
            "distinguish useful opportunities from noise and preserve evidence for "
            "qualification."
        ),
        "system_description": (
            "Provider-agnostic discovery feeding an evidence collection and "
            "qualification pipeline over structured data."
        ),
        "technical_details": (
            "Provider-agnostic discovery / evidence collection / qualification logic / "
            "structured data / testing / automation"
        ),
        "result": (
            "An actively tested pipeline for turning raw discovery into prioritized, "
            "evidence-backed opportunities."
        ),
        "proof": "SOURCE CODE / DOCUMENTATION / TESTING",
        "limitations": (
            "Beta and under active testing. No claims of lead accuracy, guaranteed "
            "clients, or autonomous operation — only what testing demonstrates."
        ),
        "next_steps": (
            "Improve provider integrations, evidence quality, qualification "
            "reliability, and testing."
        ),
        "is_featured": True,
        "display_order": 3,
        "links": [],
    },
    {
        "title": "Autonomous Economic Agent",
        "slug": "autonomous-economic-agent",
        "category_slug": "r-and-d",
        "status": "PLANNING",
        "role": "Researcher / Builder",
        "short_description": (
            "A research direction exploring autonomous economic decision-making as "
            "an engineered system. Planning stage — not a deployed system."
        ),
        "description": (
            "A research and engineering direction exploring an autonomous economic "
            "system capable of identifying legitimate opportunities, gathering "
            "evidence, analyzing uncertainty, evaluating risk/reward, and allocating "
            "limited capital conservatively."
        ),
        "system_description": (
            "Architecture concepts: observe environment, discover opportunities, "
            "acquire evidence/data, validate evidence, perform deterministic and "
            "statistical analysis, estimate probability and uncertainty, evaluate "
            "expected value and risk, allocate capital conservatively, execute "
            "permitted actions, maintain an append-only event ledger."
        ),
        "result": (
            "A structured research/architecture project exploring how economic "
            "decision-making could be modeled as an engineered system."
        ),
        "proof": "ARCHITECTURE / DOCUMENTATION / RESEARCH",
        "limitations": (
            "This is not a finished autonomous financial system. Nothing is deployed, "
            "and no profits, real-world financial activity, or investment performance "
            "are claimed."
        ),
        "next_steps": "Prototype individual subsystems and validate assumptions experimentally.",
        "is_featured": False,
        "display_order": 5,
        "links": [],
    },
]

EXPERIENCES = [
    {
        "organization": "Vespera Estates",
        "role": "Operations and Marketing Support",
        "description": (
            "Real-estate operations exposure: backend and operational work, "
            "marketing and social media, promotional content, and lead-generation "
            "activity. Seeing real business workflow friction up close — messy "
            "operational data, scattered spreadsheets, manual follow-ups — is what "
            "turned into software ideas: systems that hold business information "
            "reliably instead of letting it fragment. Real business, real friction, "
            "observation, software idea."
        ),
        "start_date": None,
        "end_date": None,
        "is_current": False,
        "display_order": 0,
    },
    {
        "organization": "AVYGEN AI",
        "role": "Technical & AI Lead",
        "description": (
            "Early-stage technical leadership: programming, assigning technical "
            "tasks, reviewing work, setting technical direction, coordinating "
            "deadlines, accountability, and client onboarding. Status: beta with "
            "client onboarding underway. Coordinating technical work — not just "
            "studying it."
        ),
        "start_date": None,
        "end_date": None,
        "is_current": True,
        "display_order": 1,
    },
]

LEARNING_ITEMS = [
    {
        "title": "C",
        "description": (
            "Programming fundamentals, memory, control flow, data structures, "
            "low-level understanding. Learning to understand the systems underneath "
            "the abstractions."
        ),
        "status": "In progress",
        "category": "Fundamentals",
        "display_order": 0,
    },
    {
        "title": "Python",
        "description": (
            "Programming fundamentals, application development, automation, backend "
            "systems. Learning to understand the systems underneath the abstractions."
        ),
        "status": "In progress",
        "category": "Backend",
        "display_order": 1,
    },
    {
        "title": "SQL / databases",
        "description": (
            "Data modeling, relationships, queries, persistence. Learning to "
            "understand the systems underneath the abstractions."
        ),
        "status": "In progress",
        "category": "Data",
        "display_order": 2,
    },
    {
        "title": "Web application architecture",
        "description": (
            "HTTP, Flask, server-rendered applications, authentication, CRUD, "
            "security. Learning to understand the systems underneath the abstractions."
        ),
        "status": "In progress",
        "category": "Backend",
        "display_order": 3,
    },
]

# Project model fields managed by the seed (everything except identity,
# timestamps, and relationships handled separately).
PROJECT_FIELDS = [
    "title", "short_description", "description", "status", "role", "problem",
    "why", "system_description", "technical_details", "decisions", "result",
    "proof", "learning", "limitations", "next_steps", "is_featured",
    "display_order",
]


def seed_portfolio():
    """Insert/update the portfolio dataset. Returns counts dict."""

    counts = {"created": 0, "updated": 0, "unchanged": 0}

    categories = {}
    for data in CATEGORIES:
        category = ProjectCategory.query.filter_by(slug=data["slug"]).first()
        if category is None:
            category = ProjectCategory(
                name=data["name"], slug=data["slug"],
                description=data["description"],
            )
            db.session.add(category)
            counts["created"] += 1
        else:
            if _apply(category, data):
                counts["updated"] += 1
            else:
                counts["unchanged"] += 1
        db.session.flush()  # assign ids for project category links
        categories[data["slug"]] = category

    for data in PROJECTS:
        project = Project.query.filter_by(slug=data["slug"]).first()
        values = {field: data.get(field) for field in PROJECT_FIELDS}
        values["category_id"] = categories[data["category_slug"]].id
        if project is None:
            project = Project(slug=data["slug"], **values)
            db.session.add(project)
            counts["created"] += 1
        elif _apply(project, values):
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
        db.session.flush()
        for link_data in data.get("links", []):
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

    for data in EXPERIENCES:
        experience = Experience.query.filter_by(
            organization=data["organization"]
        ).first()
        values = {k: v for k, v in data.items()}
        if experience is None:
            db.session.add(Experience(**values))
            counts["created"] += 1
        elif _apply(experience, values):
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    for data in LEARNING_ITEMS:
        item = LearningItem.query.filter_by(title=data["title"]).first()
        values = {k: v for k, v in data.items()}
        if item is None:
            db.session.add(LearningItem(**values))
            counts["created"] += 1
        elif _apply(item, values):
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    for data in PROJECT_MEDIA:
        project = Project.query.filter_by(slug=data["project_slug"]).first()
        if project is None:
            continue  # never invent a project row from media data
        media = ProjectMedia.query.filter_by(
            project_id=project.id, file_path=data["file_path"]
        ).first()
        values = {
            "media_type": data["media_type"],
            "alt_text": data["alt_text"],
            "caption": data["caption"],
            "display_order": data["display_order"],
            "is_primary": data["is_primary"],
        }
        if media is None:
            db.session.add(
                ProjectMedia(
                    project_id=project.id, file_path=data["file_path"], **values
                )
            )
            counts["created"] += 1
        elif _apply(media, values):
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    db.session.commit()
    return counts


def _apply(obj, values):
    """Set fields that differ. Returns True if anything changed."""
    changed = False
    for key, value in values.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            changed = True
    return changed