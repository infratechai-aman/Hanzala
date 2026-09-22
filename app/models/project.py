"""Portfolio models: categories, projects, links, media.

`status` fields are plain strings on purpose — no enum infrastructure —
so values (COMPLETED, PROTOTYPE, BETA, R&D, PLANNING, ...) stay easy
to change. Category names are content rows, not DB constraints.
"""

from datetime import datetime, timezone

from app.models import db


class ProjectCategory(db.Model):
    __tablename__ = "project_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Deleting a category does not delete its projects (category_id is
    # nullable with SET NULL); only project -> links/media cascade.
    projects = db.relationship("Project", back_populates="category")


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("project_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    short_description = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="COMPLETED", index=True)
    role = db.Column(db.String(200), nullable=True)
    problem = db.Column(db.Text, nullable=True)
    why = db.Column(db.Text, nullable=True)
    system_description = db.Column(db.Text, nullable=True)
    technical_details = db.Column(db.Text, nullable=True)
    decisions = db.Column(db.Text, nullable=True)
    result = db.Column(db.Text, nullable=True)
    proof = db.Column(db.Text, nullable=True)
    learning = db.Column(db.Text, nullable=True)
    limitations = db.Column(db.Text, nullable=True)
    next_steps = db.Column(db.Text, nullable=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    category = db.relationship("ProjectCategory", back_populates="projects")
    links = db.relationship(
        "ProjectLink",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectLink.display_order",
    )
    media = db.relationship(
        "ProjectMedia",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectMedia.display_order",
    )


class ProjectMedia(db.Model):
    __tablename__ = "project_media"

    # Renderable kinds. Anything else is kept as metadata only and the
    # public template shows it as a plain record, never as media.
    MEDIA_TYPES = ("image", "video")

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Metadata only — no upload handling in this milestone.
    media_type = db.Column(db.String(20), nullable=False, default="image")
    file_path = db.Column(db.String(500), nullable=False)
    alt_text = db.Column(db.String(255), nullable=True)
    caption = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    project = db.relationship("Project", back_populates="media")


class ProjectLink(db.Model):
    __tablename__ = "project_links"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(2000), nullable=False)
    link_type = db.Column(db.String(50), nullable=True, index=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    project = db.relationship("Project", back_populates="links")