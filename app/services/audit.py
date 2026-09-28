from flask import request, has_request_context
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def log(action, entity=None, entity_id=None, details=None):
    rec = AuditLog(action=action, entity=entity, entity_id=entity_id, details=details)
    if has_request_context():
        rec.ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if current_user.is_authenticated:
            rec.user_id = current_user.id
            rec.username = current_user.username
    db.session.add(rec)
    return rec
