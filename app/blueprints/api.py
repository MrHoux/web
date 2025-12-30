from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Product, Category, WishlistItem, ProductStatus
from app.middleware import role_required
from app.services.recommendation_service import get_homepage_recommendations
from app.services.search_service import search_products
from app.services.baidu_map_service import validate_address
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__)


@bp.route('/api/public/home', methods=['GET'])
def public_home():
    categories = Category.query.filter_by(is_active=True).limit(10).all()

    # Unauthenticated users: show popular products
    products = Product.query.filter_by(
        is_deleted=False,
        status=ProductStatus.ACTIVE
    ).order_by(Product.id.desc()).limit(12).all()

    if current_user.is_authenticated:
        products = get_homepage_recommendations(current_user.id, limit=12)

    return jsonify({
        'featured_products': [{
            'id': p.id,
            'title': p.title,
            'price': float(p.price),
            'description': p.description
        } for p in products],
        'top_categories': [{
            'id': c.id,
            'name': c.name,
            'slug': c.slug
        } for c in categories]
    })


@bp.route('/api/search', methods=['GET'])
def api_search():
    query = request.args.get('q', '').strip()
    category_slug = request.args.get('category', '').strip()
    sort_by = request.args.get('sort', 'relevance')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = request.args.get('per_page', 20, type=int)
    if per_page > 50:
        per_page = 50

    result = search_products(
        query=query if query else None,
        category_slug=category_slug if category_slug else None,
        sort_by=sort_by,
        page=page,
        per_page=per_page
    )

    return jsonify({
        'items': [{
            'id': p.id,
            'title': p.title,
            'price': float(p.price),
            'description': p.description
        } for p in result['items']],
        'page': result['page'],
        'total': result['total'],
        'pages': result['pages']
    })


@bp.route('/api/recommendations', methods=['GET'])
@login_required
def api_recommendations():
    product_id = request.args.get('product_id', type=int)
    for_user = request.args.get('for_user')

    if product_id:
        # Product detail page recommendations
        from app.services.recommendation_service import (
            get_product_recommendations,
        )
        products = get_product_recommendations(product_id, limit=6)
    elif for_user == 'me' or for_user is None:
        # Homepage recommendations
        products = get_homepage_recommendations(current_user.id, limit=12)
    else:
        products = []

    return jsonify({
        'items': [{
            'id': p.id,
            'title': p.title,
            'price': float(p.price)
        } for p in products]
    })


@bp.route('/api/wishlist/toggle', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def toggle_wishlist():
    data = request.get_json()
    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'error': 'Product ID cannot be empty'}), 400

    # Check if product exists
    Product.query.filter_by(
        id=product_id,
        is_deleted=False
    ).first_or_404()

    # Check if already in wishlist
    wishlist_item = WishlistItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()

    if wishlist_item:
        # Remove from wishlist
        db.session.delete(wishlist_item)
        in_wishlist = False
    else:
        # Add to wishlist
        wishlist_item = WishlistItem(
            user_id=current_user.id,
            product_id=product_id
        )
        db.session.add(wishlist_item)
        in_wishlist = True

    db.session.commit()

    return jsonify({
        'ok': True,
        'in_wishlist': in_wishlist
    })


@bp.route('/api/wishlist', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def get_wishlist():
    ids = [
        w.product_id for w in WishlistItem.query.filter_by(
            user_id=current_user.id).all()]
    return jsonify({'product_ids': ids})


@bp.route('/api/address/validate', methods=['POST'])
@login_required
def validate_address_api():
    data = request.get_json()
    address_data = data.get('address', {})

    result = validate_address(address_data)
    return jsonify(result)
