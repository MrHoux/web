from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    Category,
    Product,
    User,
    UserRole,
    ModerationRequest,
    ModerationStatus,
    AfterSaleRequest,
    AfterSaleStatus,
    AfterSaleType,
    Review,
    OrderGroup,
    MerchantOrder,
    MerchantOrderStatus,
    ItemStatus,
    PaymentStatus)
from app.middleware import role_required
from app.services.audit_service import log_audit
from app.utils import wants_json_response
from datetime import datetime
import logging
from sqlalchemy.orm import aliased

logger = logging.getLogger(__name__)

bp = Blueprint('admin', __name__)


def _maybe_mark_payment_refunded(order: MerchantOrder) -> None:
    if not order or not order.payment:
        return
    if order.payment.status == PaymentStatus.REFUNDED:
        return
    items = list(order.items)
    if not items:
        return
    refundable_statuses = {ItemStatus.REFUNDED, ItemStatus.RETURNED}
    if all(i.item_status in refundable_statuses for i in items):
        order.payment.status = PaymentStatus.REFUNDED


@bp.route('/admin', methods=['GET'])
@bp.route('/admin/dashboard', methods=['GET'])
@login_required
@role_required('ADMIN')
def dashboard():
    stats = {
        'total_users': User.query.count(),
        'total_merchants': User.query.filter_by(
            role=UserRole.MERCHANT).count(),
        'total_products': Product.query.filter_by(
            is_deleted=False).count(),
        'total_orders': OrderGroup.query.count(),
        'total_reviews': Review.query.filter_by(
                is_deleted=False).count(),
        'total_categories': Category.query.filter_by(
                    is_active=True).count()}

    # If JSON request, return JSON
    if wants_json_response():
        return jsonify(stats)

    # Otherwise render HTML template
    return render_template('admin/dashboard.html', stats=stats)


@bp.route('/admin/orders', methods=['GET'])
@login_required
@role_required('ADMIN')
def admin_orders():
    if wants_json_response():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = (request.args.get('status') or '').strip().upper()

        query = MerchantOrder.query.filter_by(is_deleted=False)
        if status:
            try:
                query = query.filter(
                    MerchantOrder.status == MerchantOrderStatus[status])
            except KeyError:
                pass

        orders = query.order_by(MerchantOrder.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Enrich with customer + merchant email
        merchant_u = aliased(User)
        customer_u = aliased(User)
        rows = db.session.query(
            MerchantOrder.id,
            MerchantOrder.status,
            MerchantOrder.subtotal_amount,
            MerchantOrder.created_at,
            MerchantOrder.merchant_id,
            OrderGroup.user_id,
            merchant_u.email.label('merchant_email'),
            customer_u.email.label('customer_email'),
        ).join(
            OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
        ).join(
            merchant_u, merchant_u.id == MerchantOrder.merchant_id
        ).join(
            customer_u, customer_u.id == OrderGroup.user_id
        ).filter(
            MerchantOrder.id.in_([o.id for o in orders.items])
        ).all()

        by_id = {r.id: r for r in rows}

        items = []
        for o in orders.items:
            row = by_id.get(o.id)
            items.append({
                'id': o.id,
                'status': o.status.value,
                'subtotal_amount': float(o.subtotal_amount),
                'created_at': o.created_at.isoformat(),
                'merchant_id': row.merchant_id if row else None,
                'merchant_email': row.merchant_email if row else None,
                'user_id': row.user_id if row else None,
                'customer_email': row.customer_email if row else None,
            })

        return jsonify({
            'items': items,
            'page': orders.page,
            'total': orders.total,
            'pages': orders.pages,
        })

    return render_template('admin/orders.html')


@bp.route('/admin/categories', methods=['GET'])
@login_required
@role_required('ADMIN')
def list_categories():
    # Return JSON for API or AJAX requests.
    if (request.is_json or
        request.path.startswith('/api/') or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '')):
        categories = Category.query.order_by(Category.name).all()
        return jsonify({
            'items': [{
                'id': c.id,
                'name': c.name,
                'slug': c.slug,
                'is_active': c.is_active
            } for c in categories]
        })

    # Otherwise render HTML template
    return render_template('admin/categories.html')


@bp.route('/admin/categories', methods=['POST'])
@login_required
@role_required('ADMIN')
def create_category():
    data = request.get_json()
    name = data.get('name', '').strip()
    slug = data.get('slug', '').strip()

    if not name or not slug:
        return jsonify({'error': 'Name and slug cannot be empty'}), 400

    # Check if slug already exists
    if Category.query.filter_by(slug=slug).first():
        return jsonify({'error': 'Slug already exists'}), 400

    category = Category(name=name, slug=slug, is_active=True)
    db.session.add(category)
    db.session.commit()

    return jsonify({
        'ok': True,
        'category': {
            'id': category.id,
            'name': category.name,
            'slug': category.slug
        }
    }), 201


@bp.route('/admin/categories/<int:category_id>', methods=['PUT', 'PATCH'])
@login_required
@role_required('ADMIN')
def update_category(category_id):
    category = Category.query.get_or_404(category_id)
    data = request.get_json()

    if 'name' in data:
        category.name = data['name'].strip()
    if 'slug' in data:
        slug = data['slug'].strip()
        # Check slug conflict
        existing = Category.query.filter_by(slug=slug).first()
        if existing and existing.id != category_id:
            return jsonify({'error': 'Slug already exists'}), 400
        category.slug = slug
    if 'is_active' in data:
        category.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/admin/categories/<int:category_id>', methods=['DELETE'])
@login_required
@role_required('ADMIN')
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/admin/moderation/<int:request_id>/approve', methods=['POST'])
@login_required
@role_required('ADMIN')
def approve_moderation(request_id):
    mod_request = ModerationRequest.query.get_or_404(request_id)

    if mod_request.status != ModerationStatus.PENDING:
        return jsonify({'error': 'Request already processed'}), 400

    data = request.get_json()
    admin_note = data.get('admin_note', '').strip()
    action = data.get('action', 'approve')  # approve or reject

    if action == 'approve':
        mod_request.status = ModerationStatus.APPROVED
        # Soft delete review
        review = Review.query.get(mod_request.target_id)
        if review:
            review.is_deleted = True
            review.is_hidden = True
            review.deleted_at = datetime.utcnow()
            review.deleted_by = current_user.id
            review.deleted_reason = mod_request.reason
    else:
        mod_request.status = ModerationStatus.REJECTED

    mod_request.reviewed_by = current_user.id
    mod_request.reviewed_at = datetime.utcnow()
    mod_request.admin_note = admin_note

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action=f'REVIEW_DELETE_{action.upper()}',
        target_type='MODERATION_REQUEST',
        target_id=request_id,
        payload={'review_id': mod_request.target_id, 'action': action}
    )

    return jsonify({'ok': True})


@bp.route('/api/admin/after-sales/<int:after_sale_id>', methods=['PATCH'])
@login_required
@role_required('ADMIN')
def admin_handle_after_sale(after_sale_id):
    after_sale = AfterSaleRequest.query.get_or_404(after_sale_id)

    data = request.get_json()
    action = data.get('action')  # ADMIN_APPROVE or ADMIN_REJECT
    note = data.get('note', '').strip()

    if action == 'ADMIN_APPROVE':
        if after_sale.type == AfterSaleType.REFUND_ONLY:
            after_sale.status = AfterSaleStatus.CLOSED
            try:
                after_sale.order_item.item_status = ItemStatus.REFUNDED
            except Exception:
                pass
            try:
                _maybe_mark_payment_refunded(after_sale.merchant_order)
            except Exception:
                pass
        else:
            after_sale.status = AfterSaleStatus.ADMIN_APPROVED
    elif action == 'ADMIN_REJECT':
        after_sale.status = AfterSaleStatus.ADMIN_REJECTED
    else:
        return jsonify({'error': 'Invalid action'}), 400

    after_sale.resolution_note = note
    after_sale.updated_at = datetime.utcnow()
    # If all after-sales are finished for this order, mark the order as
    # AFTER_SALE_ENDED.
    try:
        order = after_sale.merchant_order
        open_statuses = [
            AfterSaleStatus.REQUESTED,
            AfterSaleStatus.MERCHANT_APPROVED,
            AfterSaleStatus.IN_PROGRESS,
            AfterSaleStatus.ADMIN_APPROVED
        ]
        has_open = AfterSaleRequest.query.filter(
            AfterSaleRequest.merchant_order_id == order.id,
            AfterSaleRequest.status.in_(open_statuses)
        ).first() is not None
        if not has_open:
            order.status = MerchantOrderStatus.AFTER_SALE_ENDED
    except Exception:
        pass
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='AFTER_SALE_ADMIN_DECISION',
        target_type='AFTER_SALE_REQUEST',
        target_id=after_sale_id,
        payload={'action': action}
    )

    return jsonify({'ok': True})


@bp.route('/admin/users', methods=['GET'])
@login_required
@role_required('ADMIN')
def list_users():
    # If JSON request or AJAX request, return JSON
    if (request.is_json or
        request.path.startswith('/api/') or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '')):
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        role_filter = request.args.get('role')

        query = User.query

        if role_filter:
            try:
                role_enum = UserRole[role_filter.upper()]
                query = query.filter_by(role=role_enum)
            except KeyError:
                pass

        users = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return jsonify({
            'items': [{
                'id': u.id,
                'email': u.email,
                'role': u.role.value,
                'is_active': u.is_active,
                'created_at': u.created_at.isoformat()
            } for u in users.items],
            'page': users.page,
            'total': users.total
        })

    # Otherwise render HTML template
    return render_template('admin/users.html')


@bp.route('/api/admin/users/<int:user_id>/status', methods=['PATCH'])
@login_required
@role_required('ADMIN')
def update_user_status(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'You cannot change your own status'}), 400

    user = User.query.get_or_404(user_id)
    if user.role == UserRole.ADMIN:
        return jsonify({'error': 'Cannot change admin status'}), 400

    data = request.get_json() or {}
    if 'is_active' not in data:
        return jsonify({'error': 'is_active is required'}), 400

    user.is_active = bool(data.get('is_active'))
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='USER_STATUS_UPDATE',
        target_type='USER',
        target_id=user.id,
        payload={'is_active': user.is_active}
    )

    return jsonify({'ok': True, 'is_active': user.is_active})


@bp.route('/api/admin/orders/<int:order_id>/status', methods=['PATCH'])
@login_required
@role_required('ADMIN')
def update_order_status(order_id):
    order = MerchantOrder.query.get_or_404(order_id)
    data = request.get_json() or {}
    status_raw = (data.get('status') or '').strip().upper()
    note = (data.get('note') or '').strip() or None

    try:
        new_status = MerchantOrderStatus[status_raw]
    except KeyError:
        return jsonify({'error': 'Invalid status'}), 400

    old_status = order.status
    if old_status == new_status:
        return jsonify({'ok': True, 'status': order.status.value})

    order.status = new_status

    if new_status == MerchantOrderStatus.CANCELLED_BY_ADMIN:
        if order.payment and order.payment.status != PaymentStatus.REFUNDED:
            order.payment.status = PaymentStatus.REFUNDED
        if old_status in [
                MerchantOrderStatus.CREATED,
                MerchantOrderStatus.PAID]:
            for item in order.items:
                product = Product.query.get(item.product_id)
                if product:
                    product.stock += item.quantity

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ADMIN_ORDER_STATUS_UPDATE',
        target_type='MERCHANT_ORDER',
        target_id=order.id,
        payload={
            'from': old_status.value,
            'to': new_status.value,
            'note': note
        }
    )

    return jsonify({'ok': True, 'status': order.status.value})
