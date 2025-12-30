from flask import Blueprint, request, jsonify, render_template, url_for
from flask_login import current_user
from app.extensions import db
from app.models import (
    Product, ProductStatus, Category, Review, OrderItem,
    MerchantOrder, MerchantOrderStatus, OrderGroup
)
from app.services.search_service import search_products
from app.services.recommendation_service import get_product_recommendations
from app.utils import wants_json_response, get_product_rating_summary
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('products', __name__)

SHOP_PER_PAGE = 15  # 5 rows * 3 columns


@bp.route('/products', methods=['GET'])
def product_list():
    query = request.args.get('q', '').strip()
    # Multi-select categories: /products?category=a&category=b (also supports
    # legacy single + comma-separated)
    category_slugs = request.args.getlist('category')
    if not category_slugs:
        category_slugs = (request.args.get('category', '') or '').strip()
    # relevance|price_asc|price_desc|popularity|newest
    sort_by = request.args.get('sort', 'relevance')
    page = request.args.get('page', 1, type=int)
    # Fixed grid: 5 rows * 3 columns => 15 items per page (ignore larger
    # values)
    per_page = SHOP_PER_PAGE

    result = search_products(
        query=query if query else None,
        category_slug=category_slugs if category_slugs else None,
        sort_by=sort_by,
        page=page,
        per_page=per_page
    )

    # Get categories for sidebar
    categories = Category.query.filter_by(is_active=True).all()

    # If JSON request, return JSON
    if wants_json_response():
        items_payload = []
        for p in result['items']:
            image_url = None
            if getattr(p, 'image_path', None):
                image_url = url_for('static', filename=p.image_path)
            items_payload.append({
                'id': p.id,
                'title': p.title,
                'description': p.description,
                'price': float(p.price),
                'stock': p.stock,
                'merchant_id': p.merchant_id,
                'image_url': image_url,
                'created_at': p.created_at.isoformat(),
            })

        return jsonify({
            'items': items_payload,
            'page': result['page'],
            'total': result['total'],
            'pages': result['pages'],
            'per_page': result['per_page'],
        })

    # Otherwise render HTML template
    return render_template(
        'products/list.html',
        items=result['items'],
        page=result['page'],
        total=result['total'],
        pages=result['pages'],
        categories=categories,
        rating_summary=get_product_rating_summary(
            [
                p.id for p in result['items']]))


@bp.route('/c/<slug>', methods=['GET'])
def category_page(slug):
    category = Category.query.filter_by(
        slug=slug, is_active=True).first_or_404()

    page = request.args.get('page', 1, type=int)
    per_page = SHOP_PER_PAGE

    selected = request.args.getlist('category')
    if slug not in selected:
        selected = [slug] + selected

    result = search_products(
        category_slug=selected,
        sort_by='popularity',
        page=page,
        per_page=per_page
    )

    # Get categories for sidebar
    categories = Category.query.filter_by(is_active=True).all()

    # If JSON request, return JSON
    if wants_json_response():
        items_payload = []
        for p in result['items']:
            image_url = None
            if getattr(p, 'image_path', None):
                image_url = url_for('static', filename=p.image_path)
            items_payload.append({
                'id': p.id,
                'title': p.title,
                'price': float(p.price),
                'stock': p.stock,
                'image_url': image_url,
            })
        return jsonify({
            'category': {
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
            },
            'items': items_payload,
            'page': result['page'],
            'total': result['total'],
        })

    # Otherwise render HTML template
    return render_template(
        'products/list.html',
        items=result['items'],
        page=result['page'],
        total=result['total'],
        pages=result['pages'],
        categories=categories,
        current_category=category,
        rating_summary=get_product_rating_summary(
            [
                p.id for p in result['items']]))


@bp.route('/p/<int:product_id>', methods=['GET'])
def product_detail(product_id):
    product = Product.query.filter_by(
        id=product_id,
        is_deleted=False,
        status=ProductStatus.ACTIVE
    ).first_or_404()

    # Get product categories
    categories = [pc.category for pc in product.categories]

    # Get reviews (not deleted)
    reviews = Review.query.filter_by(
        product_id=product_id,
        is_deleted=False,
        is_hidden=False
    ).order_by(Review.created_at.desc()).limit(20).all()

    # Get recommended products
    recommendations = get_product_recommendations(product_id, limit=6)
    rating_summary = get_product_rating_summary(
        [product.id] + [p.id for p in recommendations])
    product_rating = rating_summary.get(product.id)

    can_review = False
    if current_user.is_authenticated and getattr(
            current_user.role, 'value', None) == 'CUSTOMER':
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
        can_review = purchased is not None

    # If JSON request, return JSON
    if wants_json_response():
        return jsonify({
            'product': {
                'id': product.id,
                'title': product.title,
                'description': product.description,
                'price': float(product.price),
                'stock': product.stock,
                'merchant_id': product.merchant_id,
                'created_at': product.created_at.isoformat()
            },
            'categories': [{
                'id': c.id,
                'name': c.name,
                'slug': c.slug
            } for c in categories],
            'reviews': [{
                'id': r.id,
                'user_id': r.user_id,
                'rating': r.rating,
                'content': r.content,
                'created_at': r.created_at.isoformat()
            } for r in reviews],
            'recommendations': [{
                'id': p.id,
                'title': p.title,
                'price': float(p.price)
            } for p in recommendations]
        })

    # Otherwise render HTML template
    return render_template('products/detail.html',
                           product=product,
                           categories=categories,
                           reviews=reviews,
                           recommendations=recommendations,
                           can_review=can_review,
                           rating_summary=rating_summary,
                           product_rating=product_rating)
