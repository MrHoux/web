from flask import Blueprint, render_template, jsonify
from flask_login import current_user
from app.models import Category, Product, ProductStatus, User, MerchantProfile
from app.services.recommendation_service import get_homepage_recommendations
from app.utils import wants_json_response, get_product_rating_summary

bp = Blueprint('public', __name__)


def _category_icon(slug: str) -> str:
    s = (slug or '').lower()
    # heuristic mapping (common e-commerce categories)
    if any(k in s for k in ['phone', 'mobile']):
        return 'bi-phone'
    if any(k in s for k in ['laptop', 'computer', 'pc']):
        return 'bi-laptop'
    if any(k in s for k in ['electronics', 'tech']):
        return 'bi-cpu'
    if any(k in s for k in ['fashion', 'clothing', 'apparel', 'men', 'women']):
        return 'bi-bag'
    if any(k in s for k in ['beauty', 'cosmetic', 'skincare']):
        return 'bi-droplet'
    if any(k in s for k in ['home', 'living', 'furniture']):
        return 'bi-house'
    if any(k in s for k in ['kitchen', 'cook', 'dining']):
        return 'bi-cup-hot'
    if any(k in s for k in ['sports', 'outdoor', 'fitness']):
        return 'bi-bicycle'
    if any(k in s for k in ['book', 'study']):
        return 'bi-book'
    if any(k in s for k in ['toy', 'kids', 'child']):
        return 'bi-emoji-smile'
    if any(k in s for k in ['pet']):
        return 'bi-heart-pulse'
    if any(k in s for k in ['grocery', 'food']):
        return 'bi-basket'
    return 'bi-tag'


@bp.route('/')
def index():
    # Get category entries
    categories = Category.query.filter_by(is_active=True).limit(10).all()

    # If user is authenticated, get personalized recommendations; otherwise
    # get trending products
    if current_user.is_authenticated:
        recommended_products = get_homepage_recommendations(
            current_user.id, limit=12)
    else:
        # Unauthenticated users: show trending products (ordered by
        # sales/reviews)
        recommended_products = Product.query.filter_by(
            is_deleted=False,
            status=ProductStatus.ACTIVE
        ).order_by(Product.id.desc()).limit(12).all()

    if wants_json_response():
        return jsonify({
            'featured_products': [{
                'id': p.id,
                'title': p.title,
                'price': float(p.price),
                'image_url': None  # Can be added later
            } for p in recommended_products],
            'top_categories': [{
                'id': c.id,
                'name': c.name,
                'slug': c.slug
            } for c in categories]
        })

    category_icons = {c.slug: _category_icon(c.slug) for c in categories}

    return render_template(
        'public/index.html',
        categories=categories,
        category_icons=category_icons,
        recommended_products=recommended_products,
        rating_summary=get_product_rating_summary(
            [
                p.id for p in recommended_products])) if hasattr(
        bp,
        'template_folder') else jsonify(
                    {
                        'message': 'Homepage',
                        'categories': [
                            c.name for c in categories],
                        'products_count': len(recommended_products)})


@bp.route('/store/<int:merchant_id>', methods=['GET'])
def merchant_store(merchant_id: int):
    merchant = User.query.get_or_404(merchant_id)
    profile = MerchantProfile.query.filter_by(user_id=merchant_id).first()

    products = Product.query.filter_by(
        merchant_id=merchant_id,
        is_deleted=False,
        status=ProductStatus.ACTIVE
    ).order_by(Product.id.desc()).limit(48).all()

    return render_template(
        'public/merchant_store.html',
        merchant=merchant,
        profile=profile,
        products=products,
        rating_summary=get_product_rating_summary([p.id for p in products])
    )


@bp.route('/help', methods=['GET'])
def help_center():
    return render_template('public/help.html')


@bp.route('/terms', methods=['GET'])
def terms():
    return render_template('public/terms.html')


@bp.route('/privacy', methods=['GET'])
def privacy():
    return render_template('public/privacy.html')
