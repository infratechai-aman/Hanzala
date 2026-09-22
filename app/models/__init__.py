"""Database models package.

`db` is defined here; concrete models live in sibling modules which
are imported below so they register on `db.metadata` (required for
Flask-Migrate autogeneration to see all tables). The imports come
after `db` is defined and submodules only import `db` back, so there
is no circular import.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ruff/noqa: E402,F401 -- imports register models on db.metadata
from app.models.admin_user import AdminUser
from app.models.crm import Client, Contact, Followup, Lead, Note
from app.models.document import Document
from app.models.experience import Experience
from app.models.learning import LearningItem
from app.models.media_vault import PortfolioMedia
from app.models.operations import (
    Acceptance,
    ActivityEvent,
    Approval,
    ClientProject,
    Deliverable,
    DocumentVersion,
    Invoice,
    Milestone,
    Payment,
    RevisionRequest,
)
from app.models.project import Project, ProjectCategory, ProjectLink, ProjectMedia