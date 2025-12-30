from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime

from app.extensions import db
from app.middleware import role_required
from app.models import (
    Address, WishlistItem, Review,
    Product, OrderGroup, MerchantOrder, MerchantOrderStatus,
    OrderItem, ItemStatus,
    OrderCancelRequest, AuditLog
)


bp = Blueprint('account', __name__)


def _membership_from_points(points: int):
    tiers = [
        ('Bronze', 0, 'bi-award'),
        ('Silver', 200, 'bi-gem'),
        ('Gold', 500, 'bi-trophy'),
        ('Platinum', 1000, 'bi-stars'),
    ]
    current = tiers[0]
    for t in tiers:
        if points >= t[1]:
            current = t
    idx = [t[0] for t in tiers].index(current[0])
    next_tier = tiers[idx + 1] if idx + 1 < len(tiers) else None
    return {
        'name': current[0],
        'min_points': current[1],
        'icon': current[2],
        'next': None if not next_tier else {
            'name': next_tier[0],
            'min_points': next_tier[1],
            'points_needed': max(0, next_tier[1] - points),
        }
    }


def _net_total_spent(user_id: int) -> float:
    spend_statuses = [
        MerchantOrderStatus.PAID,
        MerchantOrderStatus.SHIPPED,
        MerchantOrderStatus.DELIVERED,
        MerchantOrderStatus.COMPLETED,
        MerchantOrderStatus.AFTER_SALE,
        MerchantOrderStatus.AFTER_SALE_ENDED,
    ]
    exclude_item_statuses = [ItemStatus.REFUNDED, ItemStatus.RETURNED]

    total = db.session.query(
        func.coalesce(func.sum(OrderItem.unit_price * OrderItem.quantity), 0)
    ).join(
        MerchantOrder, OrderItem.merchant_order_id == MerchantOrder.id
    ).join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == user_id,
        MerchantOrder.is_deleted.is_(False),
        MerchantOrder.status.in_(spend_statuses),
        ~OrderItem.item_status.in_(exclude_item_statuses)
    ).scalar()
    return float(total or 0)


@bp.route('/account', methods=['GET'])
@bp.route('/account/overview', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def overview():
    now = datetime.utcnow()

    # --- Counts (lightweight)
    address_count = Address.query.filter_by(user_id=current_user.id).count()
    wishlist_count = WishlistItem.query.filter_by(
        user_id=current_user.id).count()
    review_count = Review.query.filter_by(
        user_id=current_user.id, is_deleted=False).count()

    # --- Orders base query
    base_q = MerchantOrder.query.join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        MerchantOrder.is_deleted.is_(False)
    )

    cancelled_statuses = [
        MerchantOrderStatus.CANCELLED_BY_USER,
        MerchantOrderStatus.CANCELLED_BY_MERCHANT,
        MerchantOrderStatus.CANCELLED_BY_ADMIN,
    ]
    # Cancelled orders should be visible but not counted in summary stats.
    total_orders = base_q.filter(
        ~MerchantOrder.status.in_(cancelled_statuses)).count()
    to_pay = base_q.filter(MerchantOrder.status ==
                           MerchantOrderStatus.CREATED).count()
    to_ship = base_q.filter(MerchantOrder.status ==
                            MerchantOrderStatus.PAID).count()
    shipped = base_q.filter(MerchantOrder.status ==
                            MerchantOrderStatus.SHIPPED).count()
    delivered = base_q.filter(MerchantOrder.status ==
                              MerchantOrderStatus.DELIVERED).count()

    # Pending cancel requests (paid orders beyond direct-cancel window)
    cancel_pending = OrderCancelRequest.query.filter_by(
        user_id=current_user.id,
        status='PENDING'
    ).count()

    # --- Spend + points (net of refunds/returns)
    total_spent_float = _net_total_spent(current_user.id)

    # 1 point per 1 currency unit (simple & common)
    points = int(total_spent_float)
    membership = _membership_from_points(points)

    # --- Recent orders
    recent_orders = base_q.order_by(
        MerchantOrder.created_at.desc()).limit(6).all()
    recent_ids = [o.id for o in recent_orders]

    pending_set = set()
    if recent_ids:
        pending_set = {
            r.merchant_order_id
            for r in OrderCancelRequest.query.filter(
                OrderCancelRequest.user_id == current_user.id,
                OrderCancelRequest.merchant_order_id.in_(recent_ids),
                OrderCancelRequest.status == 'PENDING'
            ).all()
        }

    auto_cancel_set = set()
    if recent_ids:
        auto_cancel_set = {
            a.target_id
            for a in AuditLog.query.filter(
                AuditLog.action == 'ORDER_AUTO_CANCEL_UNPAID',
                AuditLog.target_type == 'MERCHANT_ORDER',
                AuditLog.target_id.in_(recent_ids)
            ).all()
        }

    def display_status(order: MerchantOrder) -> str:
        raw = order.status.value
        if raw == 'PAID' and order.id in pending_set:
            return 'CANCEL_REQUEST_PENDING'
        if raw == 'CREATED' and now > order.cancel_deadline:
            return 'EXPIRED'
        if raw == 'CANCELLED_BY_USER' and order.id in auto_cancel_set:
            return 'EXPIRED'
        return raw

    recent_vm = [{
        'id': o.id,
        'status': display_status(o),
        'subtotal_amount': float(o.subtotal_amount),
        'created_at': o.created_at,
    } for o in recent_orders]

    return render_template(
        'account/overview.html',
        stats={
            'total_orders': total_orders,
            'to_pay': to_pay,
            'to_ship': to_ship,
            'shipped': shipped,
            'delivered': delivered,
            'cancel_pending': cancel_pending,
        },
        profile={
            'email': current_user.email,
            'created_at': current_user.created_at,
            'last_login_at': current_user.last_login_at,
        },
        engagement={
            'address_count': address_count,
            'wishlist_count': wishlist_count,
            'review_count': review_count,
        },
        loyalty={
            'total_spent': total_spent_float,
            'points': points,
            'membership': membership,
        },
        recent_orders=recent_vm
    )


@bp.route('/account/loyalty', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def loyalty_page():
    total_spent_float = _net_total_spent(current_user.id)
    points = int(total_spent_float)
    membership = _membership_from_points(points)
    return render_template('account/loyalty.html', loyalty={
        'total_spent': total_spent_float,
        'points': points,
        'membership': membership,
    })


@bp.route('/account/addresses', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def addresses_page():
    return render_template('account/addresses.html')


@bp.route('/api/account/addresses', methods=['GET', 'POST'])
@login_required
@role_required('CUSTOMER')
def addresses_api():
    if request.method == 'GET':
        items = Address.query.filter_by(
            user_id=current_user.id).order_by(
            Address.created_at.desc()).all()
        return jsonify({'items': [{
            'id': a.id,
            'recipient_name': a.recipient_name,
            'phone': a.phone,
            'province': a.province,
            'city': a.city,
            'district': a.district,
            'detail_address': a.detail_address,
            'postal_code': a.postal_code,
            'created_at': a.created_at.isoformat(),
        } for a in items]})

    data = request.get_json(silent=True) or {}
    required = [
        'recipient_name',
        'phone',
        'province',
        'city',
        'district',
        'detail_address']
    for f in required:
        if not (data.get(f) or '').strip():
            return jsonify({'error': f'{f} cannot be empty'}), 400
    a = Address(
        user_id=current_user.id,
        recipient_name=data['recipient_name'].strip(),
        phone=data['phone'].strip(),
        province=data['province'].strip(),
        city=data['city'].strip(),
        district=data['district'].strip(),
        detail_address=data['detail_address'].strip(),
        postal_code=(data.get('postal_code') or '').strip() or None
    )
    db.session.add(a)
    db.session.commit()
    return jsonify({'ok': True, 'id': a.id}), 201


@bp.route('/api/account/addresses/<int:address_id>',
          methods=['PUT', 'PATCH', 'DELETE'])
@login_required
@role_required('CUSTOMER')
def address_detail_api(address_id: int):
    a = Address.query.filter_by(id=address_id,
                                user_id=current_user.id).first_or_404()
    if request.method == 'DELETE':
        db.session.delete(a)
        db.session.commit()
        return jsonify({'ok': True})

    data = request.get_json(silent=True) or {}
    for f in [
        'recipient_name',
        'phone',
        'province',
        'city',
        'district',
        'detail_address',
        'postal_code',
    ]:
        if f in data:
            val = (data.get(f) or '').strip()
            setattr(a, f, val or None)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/account/wishlist', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def wishlist_page():
    return render_template('account/wishlist.html')


@bp.route('/api/account/wishlist', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def wishlist_api():
    rows = (
        db.session.query(WishlistItem, Product)
        .join(Product, Product.id == WishlistItem.product_id)
        .filter(
            WishlistItem.user_id == current_user.id,
            Product.is_deleted.is_(False),
        )
        .order_by(WishlistItem.created_at.desc())
        .all()
    )
    return jsonify({
        'items': [{
            'product_id': p.id,
            'title': p.title,
            'price': float(p.price),
            'stock': p.stock,
            'created_at': wi.created_at.isoformat()
        } for wi, p in rows]
    })


@bp.route('/account/reviews', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def reviews_page():
    return render_template('account/reviews.html')


@bp.route('/api/account/reviews', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def reviews_api():
    rows = (
        Review.query.filter_by(
            user_id=current_user.id,
            is_deleted=False
        )
        .order_by(Review.created_at.desc())
        .limit(100)
        .all()
    )
    # Join product info safely
    items = []
    for r in rows:
        p = Product.query.get(r.product_id)
        items.append({
            'id': r.id,
            'product_id': r.product_id,
            'product_title': p.title if p else None,
            'rating': r.rating,
            'content': r.content,
            'created_at': r.created_at.isoformat(),
            'follow_up_content': r.follow_up_content,
            'follow_up_created_at': (
                r.follow_up_created_at.isoformat()
                if r.follow_up_created_at
                else None
            )
        })
    return jsonify({'items': items})
