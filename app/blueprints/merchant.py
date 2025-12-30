from flask import (
    Blueprint,
    request,
    jsonify,
    abort,
    render_template,
    url_for,
    current_app,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    Product,
    ProductStatus,
    ProductCategory,
    Category,
    MerchantOrder,
    MerchantOrderStatus,
    ItemStatus,
    Shipment,
    ShippingStatus,
    ShipmentEvent,
    AfterSaleRequest,
    AfterSaleStatus,
    AfterSaleType,
    ModerationRequest,
    ModerationRequestType,
    ModerationTargetType,
    ModerationStatus,
    Review,
    OrderCancelRequest,
    PaymentStatus,
    AuditLog,
)
from app.middleware import role_required
from app.services.audit_service import log_audit
from app.utils import object_permission_required, wants_json_response
from datetime import datetime
import logging
import os
import uuid
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

bp = Blueprint('merchant', __name__)


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


@bp.route('/merchant', methods=['GET'])
@bp.route('/merchant/dashboard', methods=['GET'])
@login_required
@role_required('MERCHANT')
def dashboard():
    # KPIs
    orders_q = MerchantOrder.query.filter_by(
        merchant_id=current_user.id,
        is_deleted=False,
    )
    cancelled_statuses = [
        MerchantOrderStatus.CANCELLED_BY_USER,
        MerchantOrderStatus.CANCELLED_BY_MERCHANT,
        MerchantOrderStatus.CANCELLED_BY_ADMIN,
    ]
    # Total orders excludes cancelled per spec
    total_orders = orders_q.filter(
        ~MerchantOrder.status.in_(cancelled_statuses)).count()
    paid_to_ship = orders_q.filter(
        MerchantOrder.status == MerchantOrderStatus.PAID).count()
    in_transit = orders_q.filter(
        MerchantOrder.status == MerchantOrderStatus.SHIPPED).count()
    delivered = orders_q.filter(
        MerchantOrder.status == MerchantOrderStatus.DELIVERED).count()
    cancelled = orders_q.filter(
        MerchantOrder.status.in_(cancelled_statuses)).count()

    pending_cancel_requests = OrderCancelRequest.query.filter_by(
        merchant_id=current_user.id,
        status='PENDING'
    ).count()

    pending_after_sales = AfterSaleRequest.query.join(MerchantOrder).filter(
        MerchantOrder.merchant_id == current_user.id,
        AfterSaleRequest.status == AfterSaleStatus.REQUESTED
    ).count()

    recent_to_ship = (
        orders_q.filter(MerchantOrder.status == MerchantOrderStatus.PAID)
        .order_by(MerchantOrder.created_at.desc())
        .limit(8)
        .all()
    )

    recent_cancel_requests = (
        OrderCancelRequest.query.filter_by(
            merchant_id=current_user.id,
            status='PENDING',
        )
        .order_by(OrderCancelRequest.created_at.desc())
        .limit(8)
        .all()
    )

    recent_after_sales = (
        AfterSaleRequest.query.join(MerchantOrder)
        .filter(
            MerchantOrder.merchant_id == current_user.id,
            AfterSaleRequest.status == AfterSaleStatus.REQUESTED,
        )
        .order_by(AfterSaleRequest.created_at.desc())
        .limit(8)
        .all()
    )

    # Returns in transit (customer has shipped; merchant needs to confirm
    # receipt)
    returns_in_transit = (
        AfterSaleRequest.query.join(MerchantOrder)
        .filter(
            MerchantOrder.merchant_id == current_user.id,
            AfterSaleRequest.type == AfterSaleType.RETURN,
            AfterSaleRequest.status == AfterSaleStatus.IN_PROGRESS,
            AfterSaleRequest.return_shipping_status
            == ShippingStatus.IN_TRANSIT,
        )
        .order_by(
            AfterSaleRequest.return_shipped_at.desc().nullslast(),
            AfterSaleRequest.created_at.desc(),
        )
        .limit(8)
        .all()
    )

    return render_template(
        'merchant/dashboard.html',
        stats={
            'total_orders': total_orders,
            'paid_to_ship': paid_to_ship,
            'in_transit': in_transit,
            'delivered': delivered,
            'cancelled': cancelled,
            'pending_cancel_requests': pending_cancel_requests,
            'pending_after_sales': pending_after_sales,
        },
        recent_to_ship=recent_to_ship,
        recent_cancel_requests=recent_cancel_requests,
        recent_after_sales=recent_after_sales,
        returns_in_transit=returns_in_transit,
    )


@bp.route('/api/merchant/dashboard', methods=['GET'])
@login_required
@role_required('MERCHANT')
def dashboard_api():
    orders_q = MerchantOrder.query.filter_by(
        merchant_id=current_user.id,
        is_deleted=False,
    )
    cancelled_statuses = [
        MerchantOrderStatus.CANCELLED_BY_USER,
        MerchantOrderStatus.CANCELLED_BY_MERCHANT,
        MerchantOrderStatus.CANCELLED_BY_ADMIN,
    ]

    stats = {
        # Total orders exclude cancelled per spec.
        'total_orders': orders_q.filter(
            ~MerchantOrder.status.in_(cancelled_statuses)
        ).count(),
        'paid_to_ship': orders_q.filter(
            MerchantOrder.status == MerchantOrderStatus.PAID
        ).count(),
        'in_transit': orders_q.filter(
            MerchantOrder.status == MerchantOrderStatus.SHIPPED
        ).count(),
        'delivered': orders_q.filter(
            MerchantOrder.status == MerchantOrderStatus.DELIVERED
        ).count(),
        'cancelled': orders_q.filter(
            MerchantOrder.status.in_(cancelled_statuses)
        ).count(),
        'pending_cancel_requests': OrderCancelRequest.query.filter_by(
            merchant_id=current_user.id,
            status='PENDING',
        ).count(),
        'pending_after_sales': (
            AfterSaleRequest.query.join(MerchantOrder)
            .filter(
                MerchantOrder.merchant_id == current_user.id,
                AfterSaleRequest.status == AfterSaleStatus.REQUESTED,
            )
            .count()
        ),
    }

    recent_to_ship = (
        orders_q.filter(MerchantOrder.status == MerchantOrderStatus.PAID)
        .order_by(MerchantOrder.created_at.desc())
        .limit(8)
        .all()
    )

    recent_cancel_requests = (
        OrderCancelRequest.query.filter_by(
            merchant_id=current_user.id,
            status='PENDING',
        )
        .order_by(OrderCancelRequest.created_at.desc())
        .limit(8)
        .all()
    )

    recent_after_sales = (
        AfterSaleRequest.query.join(MerchantOrder)
        .filter(
            MerchantOrder.merchant_id == current_user.id,
            AfterSaleRequest.status == AfterSaleStatus.REQUESTED,
        )
        .order_by(AfterSaleRequest.created_at.desc())
        .limit(8)
        .all()
    )

    returns_in_transit = (
        AfterSaleRequest.query.join(MerchantOrder)
        .filter(
            MerchantOrder.merchant_id == current_user.id,
            AfterSaleRequest.type == AfterSaleType.RETURN,
            AfterSaleRequest.status == AfterSaleStatus.IN_PROGRESS,
            AfterSaleRequest.return_shipping_status
            == ShippingStatus.IN_TRANSIT,
        )
        .order_by(
            AfterSaleRequest.return_shipped_at.desc().nullslast(),
            AfterSaleRequest.created_at.desc(),
        )
        .limit(8)
        .all()
    )

    recent_to_ship_data = [
        {
            'id': o.id,
            'subtotal_amount': float(o.subtotal_amount),
        }
        for o in recent_to_ship
    ]
    recent_cancel_data = [
        {
            'id': r.id,
            'merchant_order_id': r.merchant_order_id,
            'reason': r.reason,
            'created_at': r.created_at.isoformat(),
        }
        for r in recent_cancel_requests
    ]
    recent_after_sales_data = [
        {
            'id': a.id,
            'merchant_order_id': a.merchant_order_id,
            'order_item_id': a.order_item_id,
            'type': a.type.value,
            'created_at': a.created_at.isoformat(),
        }
        for a in recent_after_sales
    ]
    returns_in_transit_data = [
        {
            'id': a.id,
            'merchant_order_id': a.merchant_order_id,
            'order_item_id': a.order_item_id,
            'carrier_name': a.return_carrier_name,
            'tracking_no': a.return_tracking_no,
            'shipped_at': (
                a.return_shipped_at.isoformat()
                if a.return_shipped_at
                else None
            ),
        }
        for a in returns_in_transit
    ]

    return jsonify({
        'stats': stats,
        'recent_to_ship': recent_to_ship_data,
        'recent_cancel_requests': recent_cancel_data,
        'recent_after_sales': recent_after_sales_data,
        'returns_in_transit': returns_in_transit_data,
    })


@bp.route('/merchant/products', methods=['GET'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def list_products():
    # If JSON request, return JSON
    if wants_json_response():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        query = Product.query.filter_by(merchant_id=current_user.id)

        # Admin can view all
        if current_user.role.value == 'ADMIN':
            query = Product.query

        products = query.filter_by(is_deleted=False).order_by(
            Product.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        items = []
        for p in products.items:
            image_url = None
            if getattr(p, 'image_path', None):
                image_url = url_for('static', filename=p.image_path)
            merchant_email = None
            if current_user.role.value == 'ADMIN' and p.merchant:
                merchant_email = p.merchant.email
            items.append({
                'id': p.id,
                'title': p.title,
                'image_url': image_url,
                'price': float(p.price),
                'stock': p.stock,
                'status': p.status.value,
                'created_at': p.created_at.isoformat(),
                'merchant_id': (
                    p.merchant_id
                    if current_user.role.value == 'ADMIN'
                    else None
                ),
                'merchant_email': merchant_email,
            })

        return jsonify({
            'items': items,
            'page': products.page,
            'total': products.total,
            'pages': products.pages,
        })

    # Otherwise render HTML template
    return render_template('merchant/products.html')


@bp.route('/api/merchant/categories', methods=['GET'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def merchant_categories():
    items = Category.query.filter_by(
        is_active=True).order_by(
        Category.name.asc()).all()
    return jsonify({
        'items': [{
            'id': c.id,
            'name': c.name,
            'slug': c.slug
        } for c in items]
    })


@bp.route('/merchant/products', methods=['POST'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def create_product():
    data = request.get_json()
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    price = data.get('price')
    stock = data.get('stock', 0)
    category_ids = data.get('category_ids', [])

    if not title:
        return jsonify({'error': 'Product title cannot be empty'}), 400
    if price is None or price <= 0:
        return jsonify({'error': 'Price must be greater than 0'}), 400
    if stock < 0:
        return jsonify({'error': 'Stock cannot be negative'}), 400

    product = Product(
        merchant_id=current_user.id,
        title=title,
        description=description,
        price=price,
        stock=stock,
        status=ProductStatus.ACTIVE
    )
    db.session.add(product)
    db.session.flush()

    # Add categories
    if category_ids:
        valid_categories = Category.query.filter(
            Category.id.in_(category_ids),
            Category.is_active
        ).all()
        for category in valid_categories:
            pc = ProductCategory(
                product_id=product.id,
                category_id=category.id)
            db.session.add(pc)

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='PRODUCT_CREATE',
        target_type='PRODUCT',
        target_id=product.id,
        payload={
            'title': title,
            'price': float(price),
        },
    )

    image_url = None
    if getattr(product, 'image_path', None):
        image_url = url_for('static', filename=product.image_path)

    return jsonify({
        'ok': True,
        'product': {
            'id': product.id,
            'title': product.title,
            'image_url': image_url,
        },
    }), 201


@bp.route('/merchant/products/<int:product_id>', methods=['GET'])
@login_required
@role_required('MERCHANT', 'ADMIN')
@object_permission_required(Product, 'product_id', 'merchant_id')
def get_product(product_id, resource):
    product = resource

    if (
        current_user.role.value != 'ADMIN'
        and product.merchant_id != current_user.id
    ):
        abort(403)

    cat_ids = [
        pc.category_id
        for pc in ProductCategory.query.filter_by(
            product_id=product.id
        ).all()
    ]
    image_url = None
    if getattr(product, 'image_path', None):
        image_url = url_for('static', filename=product.image_path)
    return jsonify({
        'product': {
            'id': product.id,
            'title': product.title,
            'description': product.description,
            'price': float(product.price),
            'stock': product.stock,
            'status': product.status.value,
            'category_ids': cat_ids,
            'image_url': image_url,
            'image_path': getattr(product, 'image_path', None),
        }
    })


@bp.route('/merchant/products/<int:product_id>', methods=['PUT', 'PATCH'])
@login_required
@role_required('MERCHANT', 'ADMIN')
@object_permission_required(Product, 'product_id', 'merchant_id')
def update_product(product_id, resource):
    product = resource

    # Admin can modify any product
    if (
        current_user.role.value != 'ADMIN'
        and product.merchant_id != current_user.id
    ):
        abort(403)

    data = request.get_json()

    if 'title' in data:
        product.title = data['title'].strip()
    if 'description' in data:
        product.description = data['description'].strip()
    if 'price' in data:
        price = data['price']
        if price <= 0:
            return jsonify({'error': 'Price must be greater than 0'}), 400
        product.price = price
    if 'stock' in data:
        stock = data['stock']
        if stock < 0:
            return jsonify({'error': 'Stock cannot be negative'}), 400
        product.stock = stock
    if 'status' in data:
        try:
            product.status = ProductStatus[data['status']]
        except KeyError:
            return jsonify({'error': 'Invalid status'}), 400

    if 'category_ids' in data:
        # Update categories
        ProductCategory.query.filter_by(product_id=product.id).delete()
        category_ids = data['category_ids']
        if category_ids:
            valid_categories = Category.query.filter(
                Category.id.in_(category_ids),
                Category.is_active
            ).all()
            for category in valid_categories:
                pc = ProductCategory(
                    product_id=product.id,
                    category_id=category.id)
                db.session.add(pc)

    product.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='PRODUCT_UPDATE',
        target_type='PRODUCT',
        target_id=product.id
    )

    image_url = None
    if getattr(product, 'image_path', None):
        image_url = url_for('static', filename=product.image_path)
    return jsonify({
        'ok': True,
        'product': {
            'id': product.id,
            'title': product.title,
            'image_url': image_url,
        }
    })


@bp.route('/merchant/products/<int:product_id>/image', methods=['POST'])
@login_required
@role_required('MERCHANT', 'ADMIN')
@object_permission_required(Product, 'product_id', 'merchant_id')
def upload_product_image(product_id, resource):
    product = resource
    if (
        current_user.role.value != 'ADMIN'
        and product.merchant_id != current_user.id
    ):
        abort(403)

    f = request.files.get('image')
    if not f:
        return jsonify({'error': 'No image uploaded'}), 400

    filename = secure_filename(f.filename or '')
    ext = (filename.rsplit('.', 1)[-1] if '.' in filename else '').lower()
    if ext not in ('jpg', 'jpeg', 'png', 'webp'):
        return jsonify(
            {'error': 'Unsupported image type (jpg/jpeg/png/webp only)'}), 400

    # Save under static/uploads/products/
    rel_dir = os.path.join('uploads', 'products')
    abs_dir = os.path.join(current_app.static_folder, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    new_name = f"{product.id}_{uuid.uuid4().hex}.{ext}"
    abs_path = os.path.join(abs_dir, new_name)
    f.save(abs_path)

    # Best-effort cleanup old file if it was under uploads/products
    old_rel = getattr(product, 'image_path', None) or ''
    if old_rel.startswith('uploads/products/'):
        try:
            old_abs = os.path.join(current_app.static_folder, old_rel)
            if os.path.isfile(old_abs):
                os.remove(old_abs)
        except Exception:
            pass

    product.image_path = f"{rel_dir}/{new_name}".replace('\\', '/')
    product.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='PRODUCT_IMAGE_UPDATE',
        target_type='PRODUCT',
        target_id=product.id,
        payload={'ext': ext}
    )

    return jsonify({
        'ok': True,
        'image_url': url_for('static', filename=product.image_path),
        'image_path': product.image_path
    })


@bp.route('/merchant/products/<int:product_id>', methods=['DELETE'])
@login_required
@role_required('MERCHANT', 'ADMIN')
@object_permission_required(Product, 'product_id', 'merchant_id')
def delete_product(product_id, resource):
    product = resource

    if (
        current_user.role.value != 'ADMIN'
        and product.merchant_id != current_user.id
    ):
        abort(403)

    product.is_deleted = True
    product.deleted_at = datetime.utcnow()
    product.deleted_by = current_user.id
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='PRODUCT_DELETE',
        target_type='PRODUCT',
        target_id=product.id
    )

    return jsonify({'ok': True})


@bp.route('/merchant/orders', methods=['GET'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def list_merchant_orders():
    # If JSON request, return JSON
    if wants_json_response():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        query = MerchantOrder.query.filter_by(merchant_id=current_user.id)

        if current_user.role.value == 'ADMIN':
            query = MerchantOrder.query

        orders = query.filter_by(is_deleted=False).order_by(
            MerchantOrder.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        order_ids = [o.id for o in orders.items]
        pending_set = set()
        if order_ids:
            pending_set = {
                r.merchant_order_id
                for r in OrderCancelRequest.query.filter(
                    OrderCancelRequest.merchant_order_id.in_(order_ids),
                    OrderCancelRequest.status == 'PENDING'
                ).all()
            }

        auto_cancel_set = set()
        if order_ids:
            auto_cancel_set = {
                a.target_id
                for a in AuditLog.query.filter(
                    AuditLog.action == 'ORDER_AUTO_CANCEL_UNPAID',
                    AuditLog.target_type == 'MERCHANT_ORDER',
                    AuditLog.target_id.in_(order_ids)
                ).all()
            }

        now = datetime.utcnow()

        def display_status(order: MerchantOrder) -> str:
            raw = order.status.value
            if raw == 'PAID' and order.id in pending_set:
                return 'CANCEL_REQUEST_PENDING'
            if raw == 'CREATED' and now > order.cancel_deadline:
                return 'EXPIRED'
            if raw == 'CANCELLED_BY_USER' and order.id in auto_cancel_set:
                return 'EXPIRED'
            return raw

        return jsonify({
            'items': [{
                'id': order.id,
                'status': display_status(order),
                'subtotal_amount': float(order.subtotal_amount),
                'created_at': order.created_at.isoformat(),
                'items_count': order.items.count(),
                'has_pending_cancel_request': (order.id in pending_set)
            } for order in orders.items],
            'page': orders.page,
            'total': orders.total
        })

    # Otherwise render HTML template
    return render_template('merchant/orders.html')


@bp.route('/api/merchant/cancel-requests', methods=['GET'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def list_cancel_requests():
    status = request.args.get('status', 'PENDING').upper()
    if status not in ('PENDING', 'APPROVED', 'REJECTED'):
        status = 'PENDING'

    query = OrderCancelRequest.query.filter_by(status=status)
    if current_user.role.value != 'ADMIN':
        query = query.filter_by(merchant_id=current_user.id)

    items = query.order_by(
        OrderCancelRequest.created_at.desc()).limit(100).all()
    return jsonify({
        'items': [{
            'id': r.id,
            'merchant_order_id': r.merchant_order_id,
            'user_id': r.user_id,
            'merchant_id': r.merchant_id,
            'status': r.status,
            'reason': r.reason,
            'merchant_note': r.merchant_note,
            'created_at': r.created_at.isoformat(),
            'decided_at': r.decided_at.isoformat() if r.decided_at else None
        } for r in items]
    })


@bp.route('/api/merchant/cancel-requests/<int:request_id>/approve',
          methods=['POST'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def approve_cancel_request(request_id):
    req = OrderCancelRequest.query.get_or_404(request_id)
    if req.status != 'PENDING':
        return jsonify({'error': 'Request already processed'}), 400

    order = MerchantOrder.query.get_or_404(req.merchant_order_id)
    if (
        current_user.role.value != 'ADMIN'
        and order.merchant_id != current_user.id
    ):
        abort(403)

    # Only allow approval when order is paid and not deleted
    if order.is_deleted:
        return jsonify({'error': 'Order deleted'}), 400
    if order.status != MerchantOrderStatus.PAID:
        return jsonify({
            'error': 'Order status does not allow this operation'
        }), 400

    data = request.get_json(silent=True) or {}
    note = (data.get('note') or '').strip() or None

    # Mock refund
    if order.payment:
        order.payment.status = PaymentStatus.REFUNDED

    # Restore stock
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock += item.quantity

    order.status = MerchantOrderStatus.CANCELLED_BY_MERCHANT
    req.status = 'APPROVED'
    req.merchant_note = note
    req.decided_at = datetime.utcnow()

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ORDER_CANCEL_REQUEST_APPROVE',
        target_type='ORDER_CANCEL_REQUEST',
        target_id=req.id,
        payload={'order_id': order.id}
    )

    return jsonify({'ok': True, 'request_status': req.status,
                   'order_status': order.status.value})


@bp.route('/api/merchant/cancel-requests/<int:request_id>/reject',
          methods=['POST'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def reject_cancel_request(request_id):
    req = OrderCancelRequest.query.get_or_404(request_id)
    if req.status != 'PENDING':
        return jsonify({'error': 'Request already processed'}), 400

    order = MerchantOrder.query.get_or_404(req.merchant_order_id)
    if (
        current_user.role.value != 'ADMIN'
        and order.merchant_id != current_user.id
    ):
        abort(403)

    data = request.get_json(silent=True) or {}
    note = (data.get('note') or '').strip() or None

    req.status = 'REJECTED'
    req.merchant_note = note
    req.decided_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ORDER_CANCEL_REQUEST_REJECT',
        target_type='ORDER_CANCEL_REQUEST',
        target_id=req.id,
        payload={'order_id': order.id}
    )

    return jsonify({'ok': True, 'request_status': req.status})


@bp.route('/merchant/orders/<int:order_id>', methods=['DELETE'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def delete_merchant_order(order_id):
    is_admin = current_user.role.value == 'ADMIN'
    if is_admin:
        order = MerchantOrder.query.filter_by(
            id=order_id,
            is_deleted=False,
        ).first_or_404()
    else:
        order = MerchantOrder.query.filter_by(
            id=order_id,
            merchant_id=current_user.id,
            is_deleted=False
        ).first_or_404()

    data = request.get_json() or {}
    reason = data.get('reason', 'Merchant deleted')

    # Handle based on order status
    cancel_status = (
        MerchantOrderStatus.CANCELLED_BY_ADMIN
        if is_admin
        else MerchantOrderStatus.CANCELLED_BY_MERCHANT
    )

    if order.status in [
        MerchantOrderStatus.CREATED,
        MerchantOrderStatus.PAID,
    ]:
        # Directly cancel and refund
        order.status = cancel_status
        if order.payment:
            order.payment.status = PaymentStatus.REFUNDED

        # Restore stock
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock += item.quantity
    elif order.status in [
        MerchantOrderStatus.SHIPPED,
        MerchantOrderStatus.DELIVERED,
    ]:
        # Already shipped: still allow cancellation, but need to create
        # after-sales request
        order.status = cancel_status
        # Can automatically create after-sales request (simplified
        # implementation)

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ORDER_VOID_ADMIN' if is_admin else 'ORDER_VOID_MERCHANT',
        target_type='MERCHANT_ORDER',
        target_id=order.id,
        payload={
            'reason': reason,
            'order_status': order.status.value
        }
    )

    return jsonify({'ok': True})


@bp.route('/api/merchant/orders/<int:order_id>/ship', methods=['POST'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def ship_order(order_id):
    order = MerchantOrder.query.filter_by(
        id=order_id,
        merchant_id=current_user.id
    ).first_or_404()

    if order.status != MerchantOrderStatus.PAID:
        return jsonify({'error': 'Order status does not allow shipping'}), 400

    data = request.get_json()
    carrier_name = data.get('carrier_name', '').strip()
    tracking_no = data.get('tracking_no', '').strip()
    events = data.get('events', [])

    # Create or update shipment information
    shipment = Shipment.query.filter_by(merchant_order_id=order.id).first()
    if not shipment:
        shipment = Shipment(merchant_order_id=order.id)
        db.session.add(shipment)

    shipment.carrier_name = carrier_name
    shipment.tracking_no = tracking_no
    shipment.shipping_status = ShippingStatus.IN_TRANSIT
    shipment.shipped_at = datetime.utcnow()

    # Add shipment events
    if events:
        ShipmentEvent.query.filter_by(shipment_id=shipment.id).delete()
        for event_data in events:
            event_time_raw = event_data.get('event_time')
            event_time = (
                datetime.fromisoformat(event_time_raw)
                if event_time_raw
                else datetime.utcnow()
            )
            event = ShipmentEvent(
                shipment_id=shipment.id,
                event_time=event_time,
                location_text=event_data.get('location_text'),
                status_text=event_data.get('status_text'),
            )
            db.session.add(event)

    # Update order status
    order.status = MerchantOrderStatus.SHIPPED
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ORDER_SHIP',
        target_type='MERCHANT_ORDER',
        target_id=order.id,
        payload={'carrier_name': carrier_name, 'tracking_no': tracking_no}
    )

    return jsonify({'ok': True})


@bp.route('/api/merchant/orders/<int:order_id>/shipping-status',
          methods=['PATCH'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def update_shipping_status(order_id):
    order = MerchantOrder.query.filter_by(
        id=order_id,
        merchant_id=current_user.id
    ).first_or_404()

    data = request.get_json()
    shipping_status = data.get('shipping_status')

    if shipping_status not in [s.value for s in ShippingStatus]:
        return jsonify({'error': 'Invalid shipping status'}), 400

    shipment = Shipment.query.filter_by(
        merchant_order_id=order.id).first_or_404()
    shipment.shipping_status = ShippingStatus[shipping_status]

    if shipping_status == 'DELIVERED':
        shipment.delivered_at = datetime.utcnow()
        order.status = MerchantOrderStatus.DELIVERED

    db.session.commit()

    return jsonify({'ok': True})


@bp.route('/api/merchant/reviews/<int:review_id>/delete-request',
          methods=['POST'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def request_delete_review(review_id):
    review = Review.query.get_or_404(review_id)

    # Verify product belongs to this merchant
    if (
        review.product.merchant_id != current_user.id
        and current_user.role.value != 'ADMIN'
    ):
        return jsonify({'error': 'No permission to delete this review'}), 403

    data = request.get_json()
    reason = data.get('reason', '').strip()

    # Check if there is already a pending request
    existing = ModerationRequest.query.filter_by(
        target_type=ModerationTargetType.REVIEW,
        target_id=review_id,
        status=ModerationStatus.PENDING
    ).first()

    if existing:
        return jsonify(
            {'error': 'There is already a pending deletion request'}), 400

    # Create approval request
    mod_request = ModerationRequest(
        request_type=ModerationRequestType.DELETE_REVIEW,
        target_type=ModerationTargetType.REVIEW,
        target_id=review_id,
        requester_id=current_user.id,
        reason=reason,
        status=ModerationStatus.PENDING
    )
    db.session.add(mod_request)
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='REVIEW_DELETE_REQUEST',
        target_type='MODERATION_REQUEST',
        target_id=mod_request.id,
        payload={'review_id': review_id, 'reason': reason}
    )

    return jsonify({
        'ok': True,
        'moderation_request_id': mod_request.id
    }), 201


@bp.route('/api/merchant/after-sales/<int:after_sale_id>', methods=['PATCH'])
@login_required
@role_required('MERCHANT', 'ADMIN')
def handle_after_sale(after_sale_id):
    after_sale = AfterSaleRequest.query.get_or_404(after_sale_id)

    # Verify order belongs to this merchant
    if (
        after_sale.merchant_order.merchant_id != current_user.id
        and current_user.role.value != 'ADMIN'
    ):
        return jsonify(
            {'error': 'No permission to handle this after-sale request'}), 403

    data = request.get_json(silent=True) or {}

    action = data.get('action')  # APPROVE or REJECT
    # Preset info only (no optional note). Be robust to note=null or missing.
    note = (data.get('note') or '').strip()

    if action == 'APPROVE':
        # Refund-only: approve and close as success.
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
            after_sale.status = AfterSaleStatus.MERCHANT_APPROVED
    elif action == 'REJECT':
        after_sale.status = AfterSaleStatus.MERCHANT_REJECTED
        # Restore order item status if it was in an after-sale pending status
        try:
            if after_sale.order_item and after_sale.order_item.item_status in [
                ItemStatus.REFUNDING,
                ItemStatus.RETURNING,
                ItemStatus.EXCHANGING,
            ]:
                after_sale.order_item.item_status = ItemStatus.NORMAL
        except Exception:
            pass
    else:
        return jsonify({'error': 'Invalid action'}), 400

    # Use preset resolution note if none provided
    if not note:
        note = (
            'Approved by merchant'
            if action == 'APPROVE'
            else 'Rejected by merchant'
        )
    after_sale.resolution_note = note
    after_sale.updated_at = datetime.utcnow()

    # Update merchant order status: keep AFTER_SALE while any request is open;
    # otherwise AFTER_SALE_ENDED.
    try:
        order = after_sale.merchant_order
        open_statuses = [
            AfterSaleStatus.REQUESTED,
            AfterSaleStatus.MERCHANT_APPROVED,
            AfterSaleStatus.IN_PROGRESS,
            AfterSaleStatus.ADMIN_APPROVED
        ]
        has_open = (
            AfterSaleRequest.query.filter(
                AfterSaleRequest.merchant_order_id == order.id,
                AfterSaleRequest.status.in_(open_statuses),
            ).first()
            is not None
        )
        if has_open:
            if order.status != MerchantOrderStatus.AFTER_SALE:
                order.status = MerchantOrderStatus.AFTER_SALE
        else:
            order.status = MerchantOrderStatus.AFTER_SALE_ENDED
    except Exception:
        pass

    db.session.commit()

    order_status = None
    if getattr(after_sale, 'merchant_order', None):
        order_status = after_sale.merchant_order.status.value
    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='AFTER_SALE_MERCHANT_DECISION',
        target_type='AFTER_SALE_REQUEST',
        target_id=after_sale_id,
        payload={
            'action': action,
            'order_id': getattr(after_sale, 'merchant_order_id', None),
            'order_status': order_status,
        },
    )

    return jsonify({'ok': True})


@bp.route('/api/merchant/after-sales/<int:after_sale_id>/receive-return',
          methods=['POST'])
@login_required
@role_required('MERCHANT')
def receive_return(after_sale_id):
    after_sale = AfterSaleRequest.query.get_or_404(after_sale_id)
    if after_sale.merchant_order.merchant_id != current_user.id:
        return jsonify({'error': 'No permission'}), 403

    if after_sale.type != AfterSaleType.RETURN:
        return jsonify({'error': 'Not a return request'}), 400

    if (
        after_sale.status != AfterSaleStatus.IN_PROGRESS
        or after_sale.return_shipping_status != ShippingStatus.IN_TRANSIT
    ):
        return jsonify({'error': 'Return is not in transit'}), 400

    after_sale.return_shipping_status = ShippingStatus.DELIVERED
    after_sale.return_received_at = datetime.utcnow()
    after_sale.status = AfterSaleStatus.CLOSED

    # Restock on return received
    try:
        product = after_sale.order_item.product
        if product:
            product.stock += after_sale.order_item.quantity
        after_sale.order_item.item_status = ItemStatus.RETURNED
    except Exception:
        pass
    try:
        _maybe_mark_payment_refunded(after_sale.merchant_order)
    except Exception:
        pass

    db.session.commit()

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
            db.session.commit()
    except Exception:
        pass

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='AFTER_SALE_RETURN_RECEIVED',
        target_type='AFTER_SALE_REQUEST',
        target_id=after_sale_id,
        payload={
            'order_id': getattr(
                after_sale,
                'merchant_order_id',
                None),
            'order_status': (
                after_sale.merchant_order.status.value if getattr(
                    after_sale,
                    'merchant_order',
                    None) else None)})

    return jsonify({'ok': True})
