from app.extensions import db
from app.models import (
    Category,
    OrderItem,
    Product,
    ProductCategory,
    ProductStatus,
    Review,
    WishlistItem,
)
from sqlalchemy import func, or_
import re
import logging

logger = logging.getLogger(__name__)


SLUG_RE = re.compile(r'^[a-z0-9-]+$')


def _sanitize_query(query):
    if not query:
        return None
    q = str(query).replace('\x00', '').strip()
    if not q:
        return None
    q = re.sub(r'(--|/\\*|\\*/|;|["\'`\\\\#])', ' ', q)
    q = re.sub(r'\\s+', ' ', q).strip()
    return q[:80] if len(q) > 80 else q


def _normalize_category_slugs(category_slug):
    if not category_slug:
        return []
    if isinstance(category_slug, (list, tuple, set)):
        raw = [str(x).strip().lower() for x in category_slug if str(x).strip()]
        return [s for s in raw if SLUG_RE.match(s)]
    s = str(category_slug).strip().lower()
    if not s:
        return []
    if ',' in s:
        parts = [x.strip().lower() for x in s.split(',') if x.strip()]
        return [p for p in parts if SLUG_RE.match(p)]
    return [s] if SLUG_RE.match(s) else []


def search_products(
        query=None,
        category_slug=None,
        sort_by='relevance',
        page=1,
        per_page=15):
    try:
        # Base query: active and non-deleted products
        base_query = Product.query.filter_by(
            is_deleted=False,
            status=ProductStatus.ACTIVE
        )

        # Category filter
        slugs = _normalize_category_slugs(category_slug)
        if slugs:
            categories = Category.query.filter(
                Category.slug.in_(slugs),
                Category.is_active
            ).all()
            cat_ids = [c.id for c in categories]
            if cat_ids:
                base_query = base_query.join(
                    ProductCategory, Product.id == ProductCategory.product_id
                ).filter(ProductCategory.category_id.in_(cat_ids)).distinct()

        # Keyword search
        query_safe = _sanitize_query(query)
        if query_safe:
            query_lower = query_safe.lower().strip()
            base_query = base_query.filter(
                or_(
                    Product.title.ilike(f'%{query_lower}%'),
                    Product.description.ilike(f'%{query_lower}%')
                )
            )

        products = base_query.all()

        if not products:
            return {
                'items': [],
                'page': page,
                'total': 0,
                'pages': 0
            }

        # Calculate scores
        title_scores = calculate_title_match_score(
            products, query_safe) if query_safe else {}
        category_scores = calculate_category_match_score(
            products, slugs) if slugs else {}
        popularity_scores = calculate_popularity_score(products)
        price_penalties = calculate_price_penalty(products)

        # Combined score
        final_scores = {}
        for product in products:
            final_scores[product.id] = (
                3 * title_scores.get(product.id, 0) +
                2 * category_scores.get(product.id, 0) +
                1 * popularity_scores.get(product.id, 0) -
                0.1 * price_penalties.get(product.id, 0)
            )

        # Sort
        if sort_by == 'relevance':
            sorted_products = sorted(
                products, key=lambda p: final_scores.get(
                    p.id, 0), reverse=True)
        elif sort_by == 'price_asc':
            sorted_products = sorted(products, key=lambda p: float(p.price))
        elif sort_by == 'price_desc':
            sorted_products = sorted(
                products, key=lambda p: float(
                    p.price), reverse=True)
        elif sort_by == 'popularity':
            sorted_products = sorted(
                products, key=lambda p: popularity_scores.get(
                    p.id, 0), reverse=True)
        elif sort_by == 'newest':
            sorted_products = sorted(
                products, key=lambda p: p.created_at, reverse=True)
        else:
            sorted_products = sorted(
                products, key=lambda p: final_scores.get(
                    p.id, 0), reverse=True)

        # Pagination
        total = len(sorted_products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = sorted_products[start:end]

        return {
            'items': paginated_products,
            'page': page,
            'total': total,
            'pages': (total + per_page - 1) // per_page,
            'per_page': per_page
        }

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return {
            'items': [],
            'page': page,
            'total': 0,
            'pages': 0,
            'per_page': per_page
        }


def calculate_title_match_score(products, query):
    scores = {}
    query_lower = query.lower().strip()

    for product in products:
        score = 0
        title_lower = product.title.lower()

        # Prefix match has higher weight
        if title_lower.startswith(query_lower):
            score += 10

        # Contains match
        count = title_lower.count(query_lower)
        score += count * 3

        # Word match (simple version)
        query_words = query_lower.split()
        title_words = title_lower.split()
        matched_words = len(set(query_words) & set(title_words))
        score += matched_words * 2

        scores[product.id] = score

    # Normalize to 0-100
    max_score = max(scores.values()) if scores else 1
    if max_score > 0:
        scores = {
            pid: (
                score /
                max_score) *
            100 for pid,
            score in scores.items()}

    return scores


def calculate_category_match_score(products, category_slug):
    scores = {}

    slugs = _normalize_category_slugs(category_slug)
    if not slugs:
        return {p.id: 0 for p in products}

    categories = Category.query.filter(
        Category.slug.in_(slugs),
        Category.is_active
    ).all()
    cat_ids = [c.id for c in categories]
    if not cat_ids:
        return {p.id: 0 for p in products}

    for product in products:
        product_categories = [pc.category_id for pc in product.categories]
        if any(cid in product_categories for cid in cat_ids):
            scores[product.id] = 100
        else:
            scores[product.id] = 0

    return scores


def calculate_popularity_score(products):
    scores = {}

    # Count orders
    order_counts = db.session.query(
        OrderItem.product_id,
        func.count(OrderItem.id).label('order_count')
    ).group_by(OrderItem.product_id).all()
    order_dict = {pid: count for pid, count in order_counts}

    # Count wishlist items
    wishlist_counts = db.session.query(
        WishlistItem.product_id,
        func.count(WishlistItem.user_id).label('wishlist_count')
    ).group_by(WishlistItem.product_id).all()
    wishlist_dict = {pid: count for pid, count in wishlist_counts}

    # Count reviews
    review_counts = db.session.query(
        Review.product_id,
        func.count(Review.id).label('review_count')
    ).filter_by(is_deleted=False).group_by(Review.product_id).all()
    review_dict = {pid: count for pid, count in review_counts}

    # Normalize and combine
    max_order = max(order_dict.values()) if order_dict else 1
    max_wishlist = max(wishlist_dict.values()) if wishlist_dict else 1
    max_review = max(review_dict.values()) if review_dict else 1

    for product in products:
        order_score = (order_dict.get(product.id, 0) /
                       max_order) * 50 if max_order > 0 else 0
        wishlist_score = (wishlist_dict.get(product.id, 0) /
                          max_wishlist) * 30 if max_wishlist > 0 else 0
        review_score = (review_dict.get(product.id, 0) /
                        max_review) * 20 if max_review > 0 else 0
        scores[product.id] = order_score + wishlist_score + review_score

    return scores


def calculate_price_penalty(products):
    scores = {}

    if not products:
        return {}

    prices = [float(p.price) for p in products]
    max_price = max(prices) if prices else 1
    min_price = min(prices) if prices else 0

    price_range = max_price - min_price if max_price > min_price else 1

    for product in products:
        price = float(product.price)
        # Higher price gets larger penalty (normalized to 0-100)
        penalty = ((price - min_price) / price_range) * \
            100 if price_range > 0 else 0
        scores[product.id] = penalty

    return scores
