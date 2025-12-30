from flask import Blueprint, request, jsonify, render_template, url_for
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    Cart,
    CartItem,
    Product,
    OrderGroup,
    OrderStatus,
    MerchantOrder,
    MerchantOrderStatus,
    OrderItem,
    ItemStatus,
    OrderShippingSnapshot,
    PaymentTransaction,
    PaymentStatus,
    PaymentMethod,
    ShippingStatus,
    AfterSaleRequest,
    OrderCancelRequest,
    AuditLog,
    AfterSaleType,
    AfterSaleStatus)
from app.middleware import role_required
from app.services.audit_service import log_audit
from app.services.baidu_map_service import validate_address, geocode_address
from app.config import Config
from app.utils import wants_json_response
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('orders', __name__)


def _restore_order_stock(order: MerchantOrder):
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock += item.quantity


def _auto_cancel_unpaid_if_needed(order: MerchantOrder) -> bool:
    now = datetime.utcnow()
    if order.status != MerchantOrderStatus.CREATED:
        return False
    if now <= order.cancel_deadline:
        return False

    _restore_order_stock(order)
    # auto-cancel mapped to this existing status
    order.status = MerchantOrderStatus.CANCELLED_BY_USER
    db.session.commit()

    log_audit(
        actor_id=None,
        actor_role='SYSTEM',
        action='ORDER_AUTO_CANCEL_UNPAID',
        target_type='MERCHANT_ORDER',
        target_id=order.id,
        payload={'deadline': order.cancel_deadline.isoformat()}
    )
    return True


@bp.route('/api/checkout', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def checkout():
    data = request.get_json()
    address_data = data.get('address', {})

    if not address_data:
        return jsonify({'error': 'Address information cannot be empty'}), 400

    # Validate required fields
    required_fields = [
        'recipient_name',
        'phone',
        'province',
        'city',
        'district',
        'detail_address',
    ]
    for field in required_fields:
        if not address_data.get(field):
            return jsonify({'error': f'{field} cannot be empty'}), 400

    # Get cart
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not cart or not cart.items.count():
        return jsonify({'error': 'Cart is empty'}), 400

    # Group products by merchant
    merchant_products = {}
    for cart_item in cart.items:
        product = cart_item.product
        merchant_id = product.merchant_id
        if merchant_id not in merchant_products:
            merchant_products[merchant_id] = []
        merchant_products[merchant_id].append((product, cart_item.quantity))

    # Validate stock
    for merchant_id, items in merchant_products.items():
        for product, quantity in items:
            if product.stock < quantity:
                msg = f'Product {product.title} has insufficient stock'
                return jsonify({'error': msg}), 400

    # Validate address (optional: Baidu Map API)
    if Config.BAIDU_MAP_ENABLED:
        validation_result = validate_address(address_data)
        if not validation_result['valid']:
            return jsonify({
                'error': 'Address validation failed',
                'suggestions': validation_result.get('suggestions', []),
            }), 400

    # Create order group
    total_amount = sum(
        float(item.product.price) * item.quantity
        for item in cart.items
    )
    order_group = OrderGroup(
        user_id=current_user.id,
        total_amount=total_amount,
        status=OrderStatus.CREATED
    )
    db.session.add(order_group)
    db.session.flush()

    # Create merchant sub-orders
    merchant_orders_data = []
    cancel_deadline = (
        datetime.utcnow()
        + timedelta(minutes=Config.ORDER_CANCEL_WINDOW_MINUTES)
    )

    for merchant_id, items in merchant_products.items():
        subtotal = sum(
            float(product.price) * quantity
            for product, quantity in items
        )
        merchant_order = MerchantOrder(
            order_group_id=order_group.id,
            merchant_id=merchant_id,
            status=MerchantOrderStatus.CREATED,
            cancel_deadline=cancel_deadline,
            subtotal_amount=subtotal
        )
        db.session.add(merchant_order)
        db.session.flush()

        # Create order items
        for product, quantity in items:
            order_item = OrderItem(
                merchant_order_id=merchant_order.id,
                product_id=product.id,
                unit_price=product.price,
                quantity=quantity,
                item_status=ItemStatus.NORMAL
            )
            db.session.add(order_item)

            # Deduct stock
            product.stock -= quantity

        # Create address snapshot
        full_address = (
            f"{address_data['province']}{address_data['city']}"
            f"{address_data['district']}{address_data['detail_address']}"
        )
        geocode_result = geocode_address(
            full_address) if Config.BAIDU_MAP_ENABLED else {}

        shipping_snapshot = OrderShippingSnapshot(
            merchant_order_id=merchant_order.id,
            recipient_name=address_data['recipient_name'],
            phone=address_data['phone'],
            full_address_text=full_address,
            lat=geocode_result.get('lat'),
            lng=geocode_result.get('lng'),
            baidu_place_id=geocode_result.get('baidu_place_id')
        )
        db.session.add(shipping_snapshot)

        merchant_orders_data.append({
            'merchant_order_id': merchant_order.id,
            'cancel_deadline': cancel_deadline.isoformat()
        })

    # Clear cart
    CartItem.query.filter_by(cart_id=cart.id).delete()

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ORDER_CREATE',
        target_type='ORDER_GROUP',
        target_id=order_group.id,
        payload={
            'total_amount': float(total_amount),
            'merchant_count': len(merchant_orders_data),
            'merchant_order_ids': [
                x.get('merchant_order_id') for x in merchant_orders_data]})

    return jsonify({
        'order_group_id': order_group.id,
        'merchant_orders': merchant_orders_data
    }), 201


@bp.route('/checkout', methods=['GET'])
@bp.route('/orders/checkout', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def checkout_page():
    return render_template('orders/checkout.html')


@bp.route('/orders', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def order_list():
    # If JSON request, return JSON
    if wants_json_response():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        orders = MerchantOrder.query.join(
            OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
        ).filter(
            OrderGroup.user_id == current_user.id,
            MerchantOrder.is_deleted.is_(False)
        ).order_by(MerchantOrder.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        now = datetime.utcnow()
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

        items_payload = []
        for order in orders.items:
            if order.status.value == 'PAID' and order.id in pending_set:
                display_status = 'CANCEL_REQUEST_PENDING'
            else:
                is_expired = (
                    (
                        order.status.value == 'CREATED'
                        and now > order.cancel_deadline
                    )
                    or (
                        order.status.value == 'CANCELLED_BY_USER'
                        and order.id in auto_cancel_set
                    )
                )
                if is_expired:
                    display_status = 'EXPIRED'
                else:
                    display_status = order.status.value

            order_items = []
            for item in order.items:
                image_url = None
                if getattr(item.product, 'image_path', None):
                    image_url = url_for(
                        'static',
                        filename=item.product.image_path,
                    )
                order_items.append({
                    'product_id': item.product_id,
                    'product_title': item.product.title,
                    'product_image_url': image_url,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                })

            items_payload.append({
                'id': order.id,
                'order_group_id': order.order_group_id,
                'status': display_status,
                'subtotal_amount': float(order.subtotal_amount),
                'cancel_deadline': order.cancel_deadline.isoformat(),
                'created_at': order.created_at.isoformat(),
                'items': order_items,
            })

        return jsonify({
            'items': items_payload,
            'page': orders.page,
            'total': orders.total,
            'pages': orders.pages,
        })

    # Otherwise render HTML template
    return render_template('orders/list.html')


@bp.route('/orders/<int:order_id>', methods=['GET'])
@login_required
@role_required('CUSTOMER', 'ADMIN')
def order_detail(order_id):
    if current_user.role.value == 'ADMIN':
        order = MerchantOrder.query.filter_by(
            id=order_id,
            is_deleted=False
        ).first_or_404()
    else:
        order = MerchantOrder.query.join(
            OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
        ).filter(
            OrderGroup.user_id == current_user.id,
            MerchantOrder.id == order_id,
            MerchantOrder.is_deleted.is_(False)
        ).first_or_404()

    # If browser navigation (HTML), render detail page; if API/fetch (JSON),
    # return JSON payload.
    if not wants_json_response():
        return render_template('orders/detail.html', order_id=order.id)

    try:
        now = datetime.utcnow()
        has_pending = False
        if order.status == MerchantOrderStatus.PAID:
            has_pending = (
                OrderCancelRequest.query.filter_by(
                    merchant_order_id=order.id,
                    status='PENDING',
                ).first()
                is not None
            )
        has_auto_cancel_audit = AuditLog.query.filter_by(
            action='ORDER_AUTO_CANCEL_UNPAID',
            target_type='MERCHANT_ORDER',
            target_id=order.id
        ).first() is not None
        raw = order.status.value
        display = raw
        if raw == 'PAID' and has_pending:
            display = 'CANCEL_REQUEST_PENDING'
        if raw == 'CREATED' and now > order.cancel_deadline:
            display = 'EXPIRED'
        if raw == 'CANCELLED_BY_USER' and has_auto_cancel_audit:
            display = 'EXPIRED'

        # Build items carefully (product relationship can be missing in edge
        # cases)
        items_payload = []
        for item in order.items:
            prod = getattr(item, 'product', None)
            product_title = (
                prod.title if prod else f'Product #{item.product_id}'
            )
            image_url = None
            if prod and getattr(prod, 'image_path', None):
                image_url = url_for('static', filename=prod.image_path)
            items_payload.append({
                'id': item.id,
                'product_id': item.product_id,
                'product_title': product_title,
                'product_image_url': image_url,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'item_status': item.item_status.value
            })

        after_sales_query = AfterSaleRequest.query.filter_by(
            merchant_order_id=order.id)
        if current_user.role.value != 'ADMIN':
            after_sales_query = after_sales_query.filter_by(
                user_id=current_user.id)
        after_sales_rows = after_sales_query.order_by(
            AfterSaleRequest.created_at.desc()).all()

        after_sales_payload = []
        for a in after_sales_rows:
            return_info = None
            if a.type == AfterSaleType.RETURN:
                return_info = {
                    'carrier_name': a.return_carrier_name,
                    'tracking_no': a.return_tracking_no,
                    'shipping_status': (
                        a.return_shipping_status.value
                        if a.return_shipping_status
                        else None
                    ),
                    'shipped_at': (
                        a.return_shipped_at.isoformat()
                        if a.return_shipped_at
                        else None
                    ),
                    'received_at': (
                        a.return_received_at.isoformat()
                        if a.return_received_at
                        else None
                    ),
                }
            after_sales_payload.append({
                'id': a.id,
                'order_item_id': a.order_item_id,
                'type': a.type.value,
                'status': a.status.value,
                'reason': a.reason,
                'resolution_note': a.resolution_note,
                'created_at': a.created_at.isoformat(),
                'updated_at': a.updated_at.isoformat(),
                'return': return_info,
            })

        shipping_payload = None
        if order.shipping_snapshot:
            shipping_payload = {
                'recipient_name': order.shipping_snapshot.recipient_name,
                'phone': order.shipping_snapshot.phone,
                'full_address': order.shipping_snapshot.full_address_text,
            }
        payment_payload = None
        if order.payment:
            payment_payload = {
                'status': order.payment.status.value,
                'method': order.payment.payment_method.value,
            }
        shipment_payload = None
        if order.shipment:
            shipment_payload = {
                'carrier_name': order.shipment.carrier_name,
                'tracking_no': order.shipment.tracking_no,
                'shipping_status': order.shipment.shipping_status.value,
            }

        payload = {
            'id': order.id,
            'order_group_id': order.order_group_id,
            'status': display,
            'subtotal_amount': float(order.subtotal_amount),
            'cancel_deadline': order.cancel_deadline.isoformat(),
            'created_at': order.created_at.isoformat(),
            'items': items_payload,
            'after_sales': after_sales_payload,
            'shipping': shipping_payload,
            'payment': payment_payload,
            'shipment': shipment_payload,
        }
        return jsonify(payload)
    except Exception:
        raise


@bp.route('/api/orders/<int:order_id>/cancel-window', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def get_cancel_window(order_id):
    order = MerchantOrder.query.join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        MerchantOrder.id == order_id
    ).first_or_404()

    # Auto-cancel unpaid orders once expired
    auto_cancelled = _auto_cancel_unpaid_if_needed(order)

    now = datetime.utcnow()

    # Default: for CREATED (payment window)
    window_kind = 'PAYMENT'
    window_deadline = order.cancel_deadline
    remaining_seconds = int(max(0, (window_deadline - now).total_seconds()))

    # For PAID: direct-cancel window after payment
    if order.status == MerchantOrderStatus.PAID and order.payment:
        pay_time = order.payment.updated_at or order.payment.created_at
        if pay_time:
            window_kind = 'POSTPAY_CANCEL'
            window_deadline = pay_time + timedelta(
                minutes=Config.ORDER_CANCEL_WINDOW_MINUTES
            )
            remaining_seconds = int(
                max(0, (window_deadline - now).total_seconds()))

    display_status = order.status.value
    if order.status.value == 'CREATED' and now > order.cancel_deadline:
        display_status = 'EXPIRED'
    has_auto_cancel = (
        AuditLog.query.filter_by(
            action='ORDER_AUTO_CANCEL_UNPAID',
            target_type='MERCHANT_ORDER',
            target_id=order.id,
        ).first()
        is not None
    )
    if order.status.value == 'CANCELLED_BY_USER' and has_auto_cancel:
        display_status = 'EXPIRED'
    has_pending_cancel = (
        OrderCancelRequest.query.filter_by(
            merchant_order_id=order.id,
            status='PENDING',
        ).first()
        is not None
    )
    if order.status.value == 'PAID' and has_pending_cancel:
        display_status = 'CANCEL_REQUEST_PENDING'

    return jsonify({
        'remaining_seconds': remaining_seconds,
        'window_kind': window_kind,
        'window_deadline': (
            window_deadline.isoformat() if window_deadline else None
        ),
        'cancel_deadline': order.cancel_deadline.isoformat(),
        'auto_cancelled': auto_cancelled,
        'status': display_status
    })


@bp.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def cancel_order(order_id):
    order = MerchantOrder.query.join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        MerchantOrder.id == order_id
    ).first_or_404()

    now = datetime.utcnow()

    # Unpaid: cancel within deadline; after deadline auto-cancel as unpaid
    if order.status == MerchantOrderStatus.CREATED:
        if now > order.cancel_deadline:
            auto_cancelled = _auto_cancel_unpaid_if_needed(order)
            return jsonify({
                'error': 'Payment window expired',
                'auto_cancelled': auto_cancelled,
                'status': order.status.value,
            }), 400

        _restore_order_stock(order)
        order.status = MerchantOrderStatus.CANCELLED_BY_USER
        db.session.commit()

        remaining_seconds = int((order.cancel_deadline - now).total_seconds())
        log_audit(
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            action='ORDER_CANCEL_USER',
            target_type='MERCHANT_ORDER',
            target_id=order.id,
            payload={
                'remaining_seconds': remaining_seconds,
                'status_before': 'CREATED'})

        return jsonify({'ok': True, 'new_status': order.status.value})

    # Paid: within 5 minutes of payment -> direct cancel; otherwise ->
    # merchant approval request
    if order.status == MerchantOrderStatus.PAID:
        pay_time = None
        if order.payment:
            pay_time = order.payment.updated_at or order.payment.created_at

        if not pay_time:
            return jsonify({'error': 'Payment timestamp missing'}), 400

        direct_deadline = pay_time + timedelta(
            minutes=Config.ORDER_CANCEL_WINDOW_MINUTES
        )
        if now <= direct_deadline:
            # Direct cancel + mock refund
            if order.payment:
                order.payment.status = PaymentStatus.REFUNDED
            _restore_order_stock(order)
            order.status = MerchantOrderStatus.CANCELLED_BY_USER
            db.session.commit()

            log_audit(
                actor_id=current_user.id,
                actor_role=current_user.role.value,
                action='ORDER_CANCEL_USER_AFTER_PAY',
                target_type='MERCHANT_ORDER',
                target_id=order.id,
                payload={
                    'paid_at': pay_time.isoformat(),
                    'direct_deadline': direct_deadline.isoformat(),
                },
            )
            return jsonify({
                'ok': True,
                'new_status': order.status.value,
                'refunded': True,
            })

        # Create (or reuse) merchant approval request
        existing = OrderCancelRequest.query.filter_by(
            merchant_order_id=order.id,
            user_id=current_user.id,
            status='PENDING'
        ).first()
        if existing:
            return jsonify({
                'ok': True,
                'requires_merchant_approval': True,
                'request_id': existing.id,
                'status': existing.status,
            }), 202

        data = request.get_json(silent=True) or {}
        req = OrderCancelRequest(
            merchant_order_id=order.id,
            user_id=current_user.id,
            merchant_id=order.merchant_id,
            status='PENDING',
            reason=(data.get('reason') or '').strip() or None
        )
        db.session.add(req)
        db.session.commit()

        log_audit(
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            action='ORDER_CANCEL_REQUEST_CREATE',
            target_type='ORDER_CANCEL_REQUEST',
            target_id=req.id,
            payload={'order_id': order.id}
        )

        return jsonify({
            'ok': True,
            'requires_merchant_approval': True,
            'request_id': req.id,
            'status': req.status,
        }), 202

    return jsonify({'error': 'Order status does not allow cancellation'}), 400


@bp.route('/api/orders/<int:order_id>/pay', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def pay_order(order_id):
    order = MerchantOrder.query.join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        MerchantOrder.id == order_id
    ).first_or_404()

    # Auto-cancel if unpaid window expired
    if _auto_cancel_unpaid_if_needed(order):
        return jsonify({
            'error': 'Payment window expired; order auto-cancelled',
            'status': order.status.value,
        }), 400

    if order.status != MerchantOrderStatus.CREATED:
        return jsonify({'error': 'Order status does not allow payment'}), 400

    data = request.get_json()
    payment_method = data.get('method', 'MOCK')

    # Create payment transaction
    method = (
        PaymentMethod[payment_method]
        if payment_method in PaymentMethod.__members__
        else PaymentMethod.MOCK
    )
    payment = PaymentTransaction(
        merchant_order_id=order.id,
        amount=order.subtotal_amount,
        status=PaymentStatus.INIT,
        payment_method=method,
    )
    db.session.add(payment)
    db.session.flush()

    # MOCK payment: directly succeed
    payment.status = PaymentStatus.SUCCESS
    payment.provider_trade_no = (
        f"MOCK_{payment.id}_{int(datetime.utcnow().timestamp())}"
    )
    order.status = MerchantOrderStatus.PAID

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='PAYMENT_SUCCESS',
        target_type='PAYMENT_TRANSACTION',
        target_id=payment.id,
        payload={
            'amount': float(
                order.subtotal_amount),
            'method': payment_method})

    return jsonify({
        'ok': True,
        'payment_status': payment.status.value,
        'payment_id': payment.id
    })


@bp.route('/api/order-groups/<int:group_id>/pay', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def pay_order_group(group_id):
    order_group = OrderGroup.query.filter_by(
        id=group_id,
        user_id=current_user.id,
    ).first_or_404()

    orders = MerchantOrder.query.filter_by(
        order_group_id=order_group.id,
        is_deleted=False,
    ).all()
    if not orders:
        return jsonify({'error': 'No orders found in this checkout'}), 404

    # Auto-cancel unpaid orders that have expired before payment
    expired_ids = []
    for o in orders:
        if _auto_cancel_unpaid_if_needed(o):
            expired_ids.append(o.id)
    if expired_ids:
        return jsonify({
            'error': 'Payment window expired for some orders',
            'expired_order_ids': expired_ids
        }), 400

    # Allow paying CREATED orders only.
    invalid = [
        o.id
        for o in orders
        if o.status not in (
            MerchantOrderStatus.CREATED,
            MerchantOrderStatus.PAID,
        )
    ]
    if invalid:
        return jsonify({
            'error': 'Some orders are not payable',
            'order_ids': invalid
        }), 400

    payable_orders = [
        o
        for o in orders
        if o.status == MerchantOrderStatus.CREATED
    ]
    if not payable_orders:
        return jsonify({'error': 'No payable orders in this checkout'}), 400

    data = request.get_json(silent=True) or {}
    payment_method = data.get('method', 'MOCK')

    method = (
        PaymentMethod[payment_method]
        if payment_method in PaymentMethod.__members__
        else PaymentMethod.MOCK
    )
    payment_ids = []
    for order in payable_orders:
        payment = PaymentTransaction(
            merchant_order_id=order.id,
            amount=order.subtotal_amount,
            status=PaymentStatus.INIT,
            payment_method=method,
        )
        db.session.add(payment)
        db.session.flush()

        payment.status = PaymentStatus.SUCCESS
        payment.provider_trade_no = (
            f"MOCK_{payment.id}_{int(datetime.utcnow().timestamp())}"
        )
        order.status = MerchantOrderStatus.PAID
        payment_ids.append(payment.id)

    if all(o.status == MerchantOrderStatus.PAID for o in orders):
        order_group.status = OrderStatus.PAID
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='PAYMENT_GROUP_SUCCESS',
        target_type='ORDER_GROUP',
        target_id=order_group.id,
        payload={
            'merchant_order_ids': [o.id for o in payable_orders],
            'payment_ids': payment_ids,
            'method': payment_method
        }
    )

    return jsonify({
        'ok': True,
        'order_group_id': order_group.id,
        'payment_ids': payment_ids
    })


@bp.route('/api/orders/<int:order_id>/confirm-receipt', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def confirm_receipt(order_id):
    order = MerchantOrder.query.join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        MerchantOrder.id == order_id
    ).first_or_404()

    if order.status != MerchantOrderStatus.DELIVERED:
        return jsonify({
            'error': 'Order status does not allow confirming receipt'
        }), 400

    order.status = MerchantOrderStatus.COMPLETED
    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='ORDER_CONFIRM_RECEIPT',
        target_type='MERCHANT_ORDER',
        target_id=order.id
    )

    return jsonify({
        'ok': True,
        'new_status': order.status.value
    })


@bp.route('/api/orders/<int:order_id>/after-sales', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def create_after_sale(order_id):
    order = MerchantOrder.query.join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == current_user.id,
        MerchantOrder.id == order_id
    ).first_or_404()

    if order.status not in [
        MerchantOrderStatus.COMPLETED,
        MerchantOrderStatus.AFTER_SALE,
    ]:
        return jsonify({
            'error': 'Only completed orders can apply for after-sale service'
        }), 400

    data = request.get_json() or {}
    order_item_id = data.get('order_item_id')
    after_sale_type = data.get('type')
    reason = data.get('reason', '')

    if not order_item_id:
        return jsonify({'error': 'Order item ID cannot be empty'}), 400

    if after_sale_type not in [t.value for t in AfterSaleType]:
        return jsonify({'error': 'Invalid after-sale type'}), 400

    # Verify order item belongs to this order
    order_item = OrderItem.query.filter_by(
        id=order_item_id,
        merchant_order_id=order.id
    ).first_or_404()

    # Prevent duplicate open requests for the same item
    existing = AfterSaleRequest.query.filter(
        AfterSaleRequest.order_item_id == order_item_id,
        AfterSaleRequest.status.in_([
            AfterSaleStatus.REQUESTED,
            AfterSaleStatus.MERCHANT_APPROVED,
            AfterSaleStatus.IN_PROGRESS,
            AfterSaleStatus.ADMIN_APPROVED,
        ]),
    ).first()
    if existing:
        msg = 'There is already an open after-sale request for this item'
        return jsonify({'error': msg}), 400

    # Create after-sales request
    after_sale = AfterSaleRequest(
        merchant_order_id=order.id,
        order_item_id=order_item_id,
        user_id=current_user.id,
        type=AfterSaleType[after_sale_type],
        reason=reason,
        status=AfterSaleStatus.REQUESTED
    )
    db.session.add(after_sale)

    # Update order item status
    if after_sale_type == 'REFUND_ONLY':
        order_item.item_status = ItemStatus.REFUNDING
    elif after_sale_type == 'RETURN':
        order_item.item_status = ItemStatus.RETURNING
    elif after_sale_type == 'EXCHANGE':
        order_item.item_status = ItemStatus.EXCHANGING

    # Move order into after-sale state.
    # First request moves COMPLETED to AFTER_SALE.
    if order.status == MerchantOrderStatus.COMPLETED:
        order.status = MerchantOrderStatus.AFTER_SALE

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='AFTER_SALE_CREATE',
        target_type='AFTER_SALE_REQUEST',
        target_id=after_sale.id,
        payload={
            'type': after_sale_type,
            'order_item_id': order_item_id,
            'order_id': order.id,
            'order_status': order.status.value
        }
    )

    return jsonify({
        'ok': True,
        'after_sale_id': after_sale.id
    }), 201


@bp.route('/api/after-sales/<int:after_sale_id>/return-ship', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def customer_ship_return(after_sale_id):
    after_sale = AfterSaleRequest.query.get_or_404(after_sale_id)

    # Ownership check
    if after_sale.user_id != current_user.id:
        return jsonify({'error': 'No permission'}), 403

    if after_sale.type != AfterSaleType.RETURN:
        return jsonify({
            'error': 'This after-sale request is not a return'
        }), 400

    if after_sale.status not in [
        AfterSaleStatus.MERCHANT_APPROVED,
        AfterSaleStatus.ADMIN_APPROVED,
    ]:
        msg = 'Return shipment can only be provided after approval'
        return jsonify({'error': msg}), 400

    data = request.get_json() or {}
    carrier = (data.get('carrier_name') or '').strip()
    tracking = (data.get('tracking_no') or '').strip()
    if not carrier or not tracking:
        return jsonify({
            'error': 'carrier_name and tracking_no are required'
        }), 400

    after_sale.return_carrier_name = carrier
    after_sale.return_tracking_no = tracking
    after_sale.return_shipping_status = ShippingStatus.IN_TRANSIT
    after_sale.return_shipped_at = datetime.utcnow()
    after_sale.status = AfterSaleStatus.IN_PROGRESS

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='AFTER_SALE_RETURN_SHIPPED',
        target_type='AFTER_SALE_REQUEST',
        target_id=after_sale.id
    )

    return jsonify({'ok': True})
