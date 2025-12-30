import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.middleware import role_required
from app.models import (
    Review,
    Product,
    ProductStatus,
    OrderItem,
    MerchantOrder,
    MerchantOrderStatus,
    OrderGroup,
)
from app.services.audit_service import log_audit

logger = logging.getLogger(__name__)
bp = Blueprint('reviews', __name__)


@bp.route('/api/products/<int:product_id>/reviews', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def create_review(product_id):
    Product.query.filter_by(
        id=product_id,
        is_deleted=False,
        status=ProductStatus.ACTIVE
    ).first_or_404()

    data = request.get_json()
    rating = data.get('rating')
    content = data.get('content', '').strip()

    if not rating or not (1 <= rating <= 5):
        return jsonify({'error': 'Rating must be between 1 and 5'}), 400

    # Only allow review if the user has purchased this product.
    purchased = db.session.query(OrderItem.id).join(
        MerchantOrder, OrderItem.merchant_order_id == MerchantOrder.id
    ).join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        OrderItem.product_id == product_id,
        MerchantOrder.is_deleted.is_(False),
        MerchantOrder.status.in_([
            MerchantOrderStatus.PAID,
            MerchantOrderStatus.SHIPPED,
            MerchantOrderStatus.DELIVERED,
            MerchantOrderStatus.COMPLETED
        ])
    ).first()

    if not purchased:
        msg = 'Only customers who purchased this product can leave a review'
        return jsonify({'error': msg}), 403

    # Check if already reviewed.
    existing = Review.query.filter_by(
        product_id=product_id,
        user_id=current_user.id,
        is_deleted=False
    ).first()

    if existing:
        msg = 'You have already reviewed this product'
        return jsonify({'error': msg}), 400

    # Create review
    review = Review(
        product_id=product_id,
        user_id=current_user.id,
        rating=rating,
        content=content
    )
    db.session.add(review)
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='REVIEW_CREATE',
        target_type='REVIEW',
        target_id=review.id,
        payload={
            'product_id': product_id,
            'rating': rating,
        },
    )

    return jsonify({
        'ok': True,
        'review': {
            'id': review.id,
            'rating': review.rating,
            'content': review.content,
            'created_at': review.created_at.isoformat()
        }
    }), 201


@bp.route('/api/reviews/<int:review_id>/follow-up', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def add_review_follow_up(review_id):
    review = Review.query.get_or_404(review_id)

    if review.user_id != current_user.id:
        return jsonify({'error': 'No permission to update this review'}), 403

    if review.is_deleted or review.is_hidden:
        return jsonify({'error': 'Review is not available'}), 400

    if review.follow_up_content:
        return jsonify({'error': 'Follow-up already added'}), 400

    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Follow-up content is required'}), 400
    if len(content) > 1000:
        return jsonify({'error': 'Follow-up content is too long'}), 400

    review.follow_up_content = content
    review.follow_up_created_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='REVIEW_FOLLOW_UP',
        target_type='REVIEW',
        target_id=review.id,
        payload={'product_id': review.product_id}
    )

    return jsonify({
        'ok': True,
        'follow_up': {
            'content': review.follow_up_content,
            'created_at': review.follow_up_created_at.isoformat()
        }
    })


@bp.route('/api/reviews/<int:review_id>', methods=['DELETE'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)

    # Permission check: can only delete own reviews, or admin
    if (
        review.user_id != current_user.id
        and current_user.role.value != 'ADMIN'
    ):
        return jsonify({'error': 'No permission to delete this review'}), 403

    # Soft delete
    review.is_deleted = True
    review.deleted_at = datetime.utcnow()
    review.deleted_by = current_user.id
    if review.user_id == current_user.id:
        review.deleted_reason = 'User deleted'
    else:
        review.deleted_reason = 'Admin deleted'

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='REVIEW_DELETE',
        target_type='REVIEW',
        target_id=review_id,
        payload={
            'product_id': review.product_id,
            'reason': review.deleted_reason,
        }
    )

    return jsonify({'ok': True})
