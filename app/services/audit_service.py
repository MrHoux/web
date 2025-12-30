from app.extensions import db
from app.models import AuditLog
from flask import request
import logging
import json

logger = logging.getLogger(__name__)
major_logger = logging.getLogger('major_events')
if not major_logger.handlers:
    handler = logging.FileHandler('major_events.log')
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    major_logger.addHandler(handler)
    major_logger.setLevel(logging.INFO)
    major_logger.propagate = False

MAJOR_ACTION_PREFIXES = (
    'LOGIN',
    'LOGOUT',
    'REGISTER',
    'ORDER_',
    'PAYMENT_',
    'AFTER_SALE_',
)


def _should_log_major(action: str) -> bool:
    if not action:
        return False
    return action.startswith(MAJOR_ACTION_PREFIXES)


def log_audit(
        actor_id=None,
        actor_role='ANONYMOUS',
        action='',
        target_type=None,
        target_id=None,
        payload=None,
        ip=None,
        user_agent=None):
    try:
        # Get request information
        if not ip:
            ip = request.remote_addr if request else None
        if not user_agent:
            user_agent = request.headers.get('User-Agent') if request else None

        audit = AuditLog(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip=ip,
            user_agent=user_agent
        )

        if payload:
            audit.set_payload(payload)

        db.session.add(audit)
        db.session.commit()

        # Short audit line in app.log.
        path = None
        method = None
        try:
            path = request.path if request else None
            method = request.method if request else None
        except Exception:
            pass

        payload_brief = None
        try:
            if payload is not None:
                payload_brief = json.dumps(
                    payload, ensure_ascii=False, separators=(
                        ',', ':'))
                if len(payload_brief) > 600:
                    payload_brief = payload_brief[:600] + '...'
        except Exception:
            payload_brief = None

        logger.info(
            "AUDIT action=%s actor_role=%s actor_id=%s target_type=%s "
            "target_id=%s method=%s path=%s payload=%s",
            action,
            actor_role,
            actor_id,
            target_type,
            target_id,
            method,
            path,
            payload_brief,
        )

        if _should_log_major(action):
            major_logger.info(
                "action=%s actor_role=%s actor_id=%s target_type=%s "
                "target_id=%s method=%s path=%s payload=%s",
                action,
                actor_role,
                actor_id,
                target_type,
                target_id,
                method,
                path,
                payload_brief,
            )

    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)
        db.session.rollback()
