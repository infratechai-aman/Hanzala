"""Media Vault helpers: upload validation/storage, embeds, selectors.

Upload security: allowlisted extensions per type, MIME plausibility,
magic-byte signatures, size cap, server-generated filenames inside one
dedicated directory. Uploaded content is never executed; HTML/JS/SVG
are not acceptable uploads at all.
"""

import mimetypes
import os
import re
import uuid
from urllib.parse import urlparse

from flask import current_app
from werkzeug.utils import secure_filename


# Extension allowlist per media type. No HTML/JS/SVG/SWF/executables.
ALLOWED_EXTENSIONS = {
    "IMAGE": {"jpg", "jpeg", "png", "webp"},
    "VIDEO": {"mp4", "webm", "mov"},
    "PDF": {"pdf"},
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MiB per upload


def media_directory():
    """Absolute media directory, created on demand — never deleted.

    Resolved from app config (MEDIA_ROOT), never from the current
    working directory, so restarts, reloader runs, and WSGI workers all
    see the same files. Restart-safe by construction: this function
    only ensures the directory exists.
    """
    path = os.path.abspath(current_app.config["MEDIA_ROOT"])
    os.makedirs(path, exist_ok=True)
    return path


def local_media_path(location):
    """Absolute disk path for a stored location, or None.

    None means "not a local file": remote http(s) URLs, empty values,
    and anything unsafe (absolute paths, traversal, schemes) never
    resolve to the filesystem. Callers use this single resolver so the
    database keeps one canonical relative representation while the
    browser and the disk each derive their own form from it.
    """
    loc = (location or "").strip().replace("\\", "/")
    if not loc:
        return None
    if "://" in loc:
        return None
    if loc.startswith("/") or loc.startswith("~"):
        return None
    if any(segment in ("", ".", "..") for segment in loc.split("/")):
        return None
    if "\x00" in loc:
        return None
    static_base = os.path.realpath(current_app.static_folder)
    target = os.path.realpath(os.path.join(static_base, loc))
    if target != static_base and not target.startswith(static_base + os.sep):
        return None
    return target


def local_file_exists(location):
    """True when a local location actually has bytes on disk."""
    path = local_media_path(location)
    return bool(path) and os.path.isfile(path)


def storage_status(location):
    """REMOTE, PRESENT, MISSING, or NONE (empty value).

    Remote URLs need no disk check. Missing local files are reported,
    never hidden: the admin UI surfaces MISSING instead of pretending
    the media is healthy, and rows are never auto-deleted for it.
    """
    loc = (location or "").strip()
    if not loc:
        return "NONE"
    if loc.startswith("http://") or loc.startswith("https://"):
        return "REMOTE"
    return "PRESENT" if local_file_exists(loc) else "MISSING"


def location_referenced(location, exclude_project_media_id=None,
                        exclude_portfolio_media_id=None):
    """True when any database row still points at this location.

    Guards file removal: a vault file referenced by a project record
    (or vice versa) must survive the other record's deletion.
    """
    from app.models.media_vault import PortfolioMedia
    from app.models.project import ProjectMedia

    if not location:
        return False
    query = ProjectMedia.query.filter_by(file_path=location)
    if exclude_project_media_id is not None:
        query = query.filter(
            ProjectMedia.id != exclude_project_media_id
        )
    if query.first() is not None:
        return True
    query = PortfolioMedia.query.filter_by(location=location)
    if exclude_portfolio_media_id is not None:
        query = query.filter(
            PortfolioMedia.id != exclude_portfolio_media_id
        )
    return query.first() is not None


def remove_if_unreferenced(location):
    """Delete the physical file only when no row references it.

    Returns True when a file was removed. Never touches remote URLs.
    """
    if not location or location_referenced(location):
        return False
    return delete_local_file(location)


def _magic_ok(kind, head):
    """Magic-byte check on the first bytes of the upload."""
    if kind == "IMAGE":
        return (
            head.startswith(b"\x89PNG")
            or head.startswith(b"\xff\xd8\xff")
            or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
        )
    if kind == "VIDEO":
        return head[4:8] == b"ftyp" or head.startswith(b"\x1a\x45\xdf\xa3")
    if kind == "PDF":
        return head.startswith(b"%PDF")
    return False


def validate_upload(file_storage, media_type):
    """Return (extension, size) or raise ValueError with a safe message."""
    if file_storage is None or not file_storage.filename:
        raise ValueError("Choose a file to upload.")
    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        raise ValueError("File needs an extension.")
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS.get(media_type, set()):
        raise ValueError("File extension is not allowed for this media type.")
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size <= 0:
        raise ValueError("Uploaded file is empty.")
    if size > MAX_FILE_SIZE:
        raise ValueError("File is too large (max 25 MB).")
    head = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    if not _magic_ok(media_type, head):
        raise ValueError("File contents do not match its extension.")
    guessed, _ = mimetypes.guess_type(f"file.{extension}")
    if guessed is None or not guessed.startswith(
        {"IMAGE": "image/", "VIDEO": "video/", "PDF": "application/pdf"}[
            media_type
        ]
    ):
        raise ValueError("File type is not allowed.")
    return extension, size


def store_upload(file_storage, media_type):
    """Persist a validated upload; return the canonical relative location.

    The location is static-relative (e.g. uploads/media/<uuid>.mp4): the
    database stores exactly this, the browser gets /static/<location>,
    and the disk path is derived back via local_media_path. Storage
    outside the static tree cannot be browser-served, so it is refused
    loudly instead of producing rows that 404.
    """
    extension, _size = validate_upload(file_storage, media_type)
    name = f"{uuid.uuid4().hex}.{extension}"
    directory = media_directory()
    file_storage.save(os.path.join(directory, name))
    try:
        relative = os.path.relpath(
            os.path.join(directory, name), current_app.static_folder
        )
    except ValueError:
        os.remove(os.path.join(directory, name))
        raise RuntimeError("Media storage is not servable.")
    if relative.startswith(".."):
        os.remove(os.path.join(directory, name))
        raise RuntimeError(
            "Media storage must live inside the static folder."
        )
    return relative.replace("\\", "/")


def delete_local_file(location):
    """Remove a stored file only if it resolves inside the static tree.

    Returns True when a file was removed. Never follows client-supplied
    paths: anything outside the servable static folder is refused.
    """
    path = local_media_path(location)
    if path is None or not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def is_safe_external_url(value):
    """http(s) URLs with a host; rejects javascript:, data:, etc."""
    if not value or len(value) > 2000 or "\x00" in value:
        return False
    try:
        parts = urlparse(value.strip())
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


_YOUTUBE_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{6,})"
)
_VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)")


def provider_embed_url(url):
    """Embed URL for explicitly supported providers, else None.

    Only YouTube and Vimeo get iframes. Any other external URL is
    rendered as a plain outbound link — never an arbitrary iframe.
    """
    if not url:
        return None
    match = _YOUTUBE_RE.search(url)
    if match:
        return f"https://www.youtube.com/embed/{match.group(1)}"
    match = _VIMEO_RE.search(url)
    if match:
        return f"https://player.vimeo.com/video/{match.group(1)}"
    return None


def published_intro():
    """The single published INTRO item, or None (public omits section)."""
    from app.models.media_vault import PortfolioMedia

    return (
        PortfolioMedia.query.filter_by(
            context="INTRO", visibility="PUBLISHED"
        )
        .order_by(PortfolioMedia.display_order)
        .first()
    )


def published_for_context(context):
    """Published items for a placement context, ordered for display."""
    from app.models.media_vault import PortfolioMedia

    return (
        PortfolioMedia.query.filter_by(
            context=context, visibility="PUBLISHED"
        )
        .order_by(
            PortfolioMedia.display_order, PortfolioMedia.created_at.desc()
        )
        .all()
    )


def intro_conflict(exclude_id=None):
    """An already-published INTRO blocking a second one, if any."""
    from app.models.media_vault import PortfolioMedia

    query = PortfolioMedia.query.filter_by(
        context="INTRO", visibility="PUBLISHED"
    )
    if exclude_id is not None:
        query = query.filter(PortfolioMedia.id != exclude_id)
    return query.first()


def check_integrity():
    """Vault health for tests/ops: (errors list)."""
    from app.models.media_vault import PortfolioMedia

    errors = []
    for item in PortfolioMedia.query.all():
        if item.media_type == "EXTERNAL_URL":
            if not is_safe_external_url(item.location):
                errors.append(f"media #{item.id} has an unsafe URL")
        elif item.storage == "LOCAL":
            loc = (item.location or "").replace("\\", "/")
            if loc.startswith("/") or ".." in loc or "://" in loc:
                errors.append(f"media #{item.id} has an unsafe local path")
    return errors

