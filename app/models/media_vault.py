"""Portfolio Media Vault: admin-managed public media assets.

Design decision (Part 17): the existing `project_media` table is NOT
generalized. Its `project_id` is non-nullable, it has no visibility or
placement context, and several seeded project-evidence rows depend on
its exact shape. A clean separate `portfolio_media` table carries the
general vault (placement contexts, visibility lifecycle, uploads)
without risking those relationships.
"""

from datetime import datetime, timezone

from app.models import db

MEDIA_TYPES = ("IMAGE", "VIDEO", "PDF", "EXTERNAL_URL")

MEDIA_STORAGE = ("LOCAL", "EXTERNAL")

MEDIA_VISIBILITY = ("DRAFT", "PUBLISHED", "ARCHIVED")

# Page placements an item can be assigned to. PROJECT additionally
# requires project_id (validated in the route, not just the schema).
MEDIA_CONTEXTS = (
    "IDENTITY",
    "HOME",
    "INTRO",
    "WORK",
    "PROJECT",
    "R_AND_D",
    "PROCESS",
    "CONTEXT",
    "LEARNING",
    "CONTACT",
)


class PortfolioMedia(db.Model):
    __tablename__ = "portfolio_media"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    caption = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=False, index=True)
    # LOCAL: relative path under the media directory (never absolute,
    # never traversal — generated server-side). EXTERNAL: full URL.
    storage = db.Column(db.String(20), nullable=False, default="LOCAL")
    location = db.Column(db.String(2000), nullable=False)
    alt_text = db.Column(db.String(255), nullable=True)
    poster = db.Column(db.String(2000), nullable=True)
    context = db.Column(db.String(20), nullable=False, default="WORK", index=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visibility = db.Column(
        db.String(20), nullable=False, default="DRAFT", index=True
    )
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

    __table_args__ = (
        # At most one published self-introduction: ambiguous public
        # state is impossible by construction, not just convention.
        db.Index(
            "uq_published_intro",
            "context",
            unique=True,
            sqlite_where=(db.text(
                "visibility = 'PUBLISHED' AND context = 'INTRO'"
            )),
        ),
    )

    project = db.relationship("Project")

    @property
    def is_published(self):
        return self.visibility == "PUBLISHED"
