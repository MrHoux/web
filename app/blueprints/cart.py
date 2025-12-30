from flask import Blueprint, request, jsonify, render_template, url_for
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Cart, CartItem, Product, ProductStatus
from app.middleware import role_required
from app.utils import wants_json_response
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('cart', __name__)


@bp.route('/cart', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def get_cart():
    # If JSON request, return JSON
    if wants_json_response():
        cart = Cart.query.filter_by(user_id=current_user.id).first()

        if not cart:
            cart = Cart(user_id=current_user.id)
            db.session.add(cart)
            db.session.commit()

        items = CartItem.query.filter_by(cart_id=cart.id).all()

        items_payload = []
        for item in items:
            image_url = None
            if getattr(item.product, 'image_path', None):
                image_url = url_for('static', filename=item.product.image_path)
            items_payload.append({
                'product_id': item.product_id,
                'product': {
                    'id': item.product.id,
                    'title': item.product.title,
                    'price': float(item.product.price),
                    'stock': item.product.stock,
                    'image_url': image_url,
                },
                'quantity': item.quantity,
            })

        return jsonify({
            'cart_id': cart.id,
            'items': items_payload,
            'total_items': sum(item.quantity for item in items),
        })

    # Otherwise render HTML template
    return render_template('cart/cart.html')


@bp.route('/api/cart/items', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def add_cart_item():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    if not product_id:
        return jsonify({'error': 'Product ID cannot be empty'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Quantity must be greater than 0'}), 400

    # Validate product
    product = Product.query.filter_by(
        id=product_id,
        is_deleted=False,
        status=ProductStatus.ACTIVE
    ).first_or_404()

    # Check stock
    if product.stock < quantity:
        return jsonify({'error': 'Insufficient stock'}), 400

    # Get or create cart
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.session.add(cart)
        db.session.flush()

    # Check if already exists
    cart_item = CartItem.query.filter_by(
        cart_id=cart.id,
        product_id=product_id
    ).first()

    if cart_item:
        # Update quantity
        new_quantity = cart_item.quantity + quantity
        if new_quantity > product.stock:
            return jsonify({'error': 'Insufficient stock'}), 400
        cart_item.quantity = new_quantity
    else:
        # Create new
        cart_item = CartItem(
            cart_id=cart.id,
            product_id=product_id,
            quantity=quantity
        )
        db.session.add(cart_item)

    db.session.commit()

    return jsonify({
        'ok': True,
        'cart_item': {
            'product_id': cart_item.product_id,
            'quantity': cart_item.quantity
        }
    }), 201


@bp.route('/api/cart/items/<int:product_id>', methods=['PATCH'])
@login_required
@role_required('CUSTOMER')
def update_cart_item(product_id):
    data = request.get_json()
    quantity = data.get('quantity')

    if quantity is None:
        return jsonify({'error': 'Quantity cannot be empty'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Quantity must be greater than 0'}), 400

    cart = Cart.query.filter_by(user_id=current_user.id).first_or_404()
    cart_item = CartItem.query.filter_by(
        cart_id=cart.id,
        product_id=product_id
    ).first_or_404()

    # Check stock
    product = Product.query.get_or_404(product_id)
    if product.stock < quantity:
        return jsonify({'error': 'Insufficient stock'}), 400

    cart_item.quantity = quantity
    db.session.commit()

    return jsonify({
        'ok': True,
        'cart_item': {
            'product_id': cart_item.product_id,
            'quantity': cart_item.quantity
        }
    })


@bp.route('/api/cart/items/<int:product_id>', methods=['DELETE'])
@login_required
@role_required('CUSTOMER')
def delete_cart_item(product_id):
    cart = Cart.query.filter_by(user_id=current_user.id).first_or_404()
    cart_item = CartItem.query.filter_by(
        cart_id=cart.id,
        product_id=product_id
    ).first_or_404()

    db.session.delete(cart_item)
    db.session.commit()

    return jsonify({'ok': True})
