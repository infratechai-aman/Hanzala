"""Application activity helper (append-only business history).

`log_event` records what happened, when, who did it, and which record
was involved. It never updates or deletes existing rows. Callers pass
explicit ids so the helper stays usable from routes and tests.
"""

from flask import g, has_app_context, has_request_context

from app.models import db


def log_event(
    event_type,
    description,
    client_id=None,
    project_id=None,
    entity_type=None,
    entity_id=None,
    actor_id=None,
):
    """Create one ActivityEvent row and flush it (no commit).

    The actor defaults to the currently logged-in admin when available.
    """
    from app.models.operations import ActivityEvent

    if actor_id is None and has_request_context():
        user = g.get("admin_user", None)
        if user is not None:
            actor_id = user.id
    event = ActivityEvent(
        client_id=client_id,
        project_id=project_id,
        actor_id=actor_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description[:2000],
    )
    db.session.add(event)
    db.session.flush()
    return event


def client_timeline(client_id, project_ids=()):
    """Chronological application activity for a client workspace."""
    from app.models.operations import ActivityEvent

    query = ActivityEvent.query.filter(ActivityEvent.client_id == client_id)
    if project_ids:
        query = query.filter(
            (ActivityEvent.project_id.is_(None))
            | (ActivityEvent.project_id.in_(list(project_ids)))
        )
    return query.order_by(ActivityEvent.created_at.asc(), ActivityEvent.id.asc()).all()


assert has_app_context is not None  # keep flask import used if linted strictly
