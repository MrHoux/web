from functools import wraps
from flask import jsonify, request
from sqlalchemy import func
from app.extensions import db
from app.models import Review
import logging

logger = logging.getLogger(__name__)


def wants_json_response() -> bool:
    accept = request.headers.get('Accept', '') or ''
    xrw = request.headers.get('X-Requested-With')
    return (
        request.path.startswith('/api/')
        or request.is_json
        or ('application/json' in accept)
        or (xrw == 'XMLHttpRequest')
    )


def object_permission_required(
        model_class,
        id_param='id',
        owner_field='user_id'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask_login import current_user
            from flask import request, abort

            # Get resource ID
            resource_id = kwargs.get(id_param)
            if not resource_id:
                return jsonify({'error': 'Resource ID missing'}), 400

            # Query resource
            resource = model_class.query.get_or_404(resource_id)

            # Check ownership
            owner_id = getattr(resource, owner_field, None)
            role_value = getattr(current_user.role, 'value', current_user.role)
            if owner_id != current_user.id and role_value != 'ADMIN':
                logger.warning(
                    "User %s attempted to access resource %s",
                    current_user.id,
                    resource_id,
                )
                if request.path.startswith('/api/'):
                    return jsonify({
                        'error': 'No permission to access this resource'
                    }), 403
                abort(403)

            # Inject resource into kwargs
            kwargs['resource'] = resource
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def paginate_query(query, page=1, per_page=20):
    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    return {
        'items': pagination.items,
        'page': pagination.page,
        'pages': pagination.pages,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    }


def get_product_rating_summary(product_ids):
    if not product_ids:
        return {}

    rows = db.session.query(
        Review.product_id,
        Review.rating,
        func.count(Review.id)
    ).filter(
        Review.product_id.in_(product_ids),
        Review.is_deleted.is_(False),
        Review.is_hidden.is_(False)
    ).group_by(Review.product_id, Review.rating).all()

    summary = {}
    for product_id, rating, count in rows:
        entry = summary.setdefault(product_id, {
            'count': 0,
            'sum': 0,
            'percents': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        })
        entry['count'] += count
        entry['sum'] += rating * count
        entry['percents'][rating] = entry['percents'].get(rating, 0) + count

    # Normalize to avg + percents
    for product_id, entry in summary.items():
        total = entry['count']
        avg = (entry['sum'] / total) if total else 0.0
        percents = {
            k: int(round((v / total) * 100)) if total else 0
            for k, v in entry['percents'].items()
        }
        summary[product_id] = {
            'avg': avg,
            'count': total,
            'percents': percents
        }

    return summary
