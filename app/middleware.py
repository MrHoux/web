from flask import request, redirect, url_for, jsonify, abort
from flask_login import current_user
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Exact paths that never require login
LOGIN_WHITELIST = [
    '/',
    '/login',
    '/register',
    '/favicon.ico',
    '/api/public/home',
    '/api/auth/login',
    '/api/auth/register',
    '/api/search',
]


def is_public_browse_path(path: str) -> bool:
    if path == '/':
        return True
    if path.startswith('/products'):
        return True
    if path.startswith('/p/'):
        return True
    if path.startswith('/c/'):
        return True
    if path.startswith('/store/'):
        return True
    if path in ('/help', '/terms', '/privacy'):
        return True
    return False


def is_static_file(path):
    return path.startswith('/static/')


def setup_auth_middleware(app):

    @app.before_request
    def require_login():
        path = request.path
        method = request.method.upper()

        # Allow static files
        if is_static_file(path):
            return None

        # Allow whitelist paths
        if path in LOGIN_WHITELIST:
            return None

        # Allow anonymous browsing for safe methods
        if method in (
            'GET',
            'HEAD',
                'OPTIONS') and is_public_browse_path(path):
            return None

        # Check API whitelist
        if path.startswith('/api/public/'):
            return None
        if path.startswith(
                '/api/auth/login') or path.startswith('/api/auth/register'):
            return None
        if method in ('GET', 'HEAD', 'OPTIONS') and path == '/api/search':
            return None

        # Check login status
        if not current_user.is_authenticated:
            # API requests return 401, page requests redirect to login
            if path.startswith('/api/'):
                return jsonify({'error': 'Not logged in',
                               'login_required': True}), 401
            else:
                return redirect(url_for('auth.login'))

        return None


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Not logged in'}), 401
                return redirect(url_for('auth.login'))

            # allowed_roles is a list of role names.
            if current_user.role.value not in allowed_roles:
                logger.warning(
                    "User %s attempted to access roles %s, current role: %s",
                    current_user.id,
                    allowed_roles,
                    current_user.role.value,
                )
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Insufficient permissions'}), 403
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator
