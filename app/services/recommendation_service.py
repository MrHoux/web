from app.extensions import db
from app.models import (
    Product, ProductStatus, UserInterest, OrderItem, WishlistItem,
    Review, ProductCategory, MerchantOrder, OrderGroup
)
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)


def get_homepage_recommendations(user_id, limit=12):
    try:
        # 1. Get user interest categories (40% weight)
        user_interests = UserInterest.query.filter_by(user_id=user_id).all()
        interest_category_ids = [ui.category_id for ui in user_interests]

        # 2. Get all active products
        products = Product.query.filter_by(
            is_deleted=False,
            status=ProductStatus.ACTIVE
        ).all()

        if not products:
            return []

        # Calculate scores
        interest_scores = calculate_interest_score(
            products, interest_category_ids)
        co_purchase_scores = calculate_co_purchase_score(products, user_id)
        popularity_scores = calculate_popularity_score(products)
        similarity_scores = calculate_category_similarity_score(
            products, interest_category_ids)

        # Final weighted score
        final_scores = {}
        for product in products:
            final_scores[product.id] = (
                0.4 * interest_scores.get(product.id, 0) +
                0.3 * co_purchase_scores.get(product.id, 0) +
                0.2 * popularity_scores.get(product.id, 0) +
                0.1 * similarity_scores.get(product.id, 0)
            )

        # Sort by score and return top N
        sorted_products = sorted(
            products, key=lambda p: final_scores.get(
                p.id, 0), reverse=True)
        return sorted_products[:limit]

    except Exception as e:
        logger.error(f"Recommendation algorithm error: {e}", exc_info=True)
        # Fallback: return newest products
        return Product.query.filter_by(
            is_deleted=False,
            status=ProductStatus.ACTIVE
        ).order_by(Product.created_at.desc()).limit(limit).all()


def calculate_interest_score(products, interest_category_ids):
    scores = {}

    if not interest_category_ids:
        # No interest categories, return 0 score
        return {p.id: 0 for p in products}

    for product in products:
        score = 0
        # Get product categories
        product_categories = [pc.category_id for pc in product.categories]
        # Calculate matched category count
        matched = len(set(product_categories) & set(interest_category_ids))
        if matched > 0:
            score = matched / len(interest_category_ids) * \
                100  # Normalize to 0-100
        scores[product.id] = score

    return scores


def calculate_co_purchase_score(products, user_id):
    scores = {}

    # Get product IDs from user's order history
    user_orders = db.session.query(OrderItem.product_id).join(
        MerchantOrder, OrderItem.merchant_order_id == MerchantOrder.id
    ).join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == user_id
    ).distinct().all()

    user_product_ids = [pid[0] for pid in user_orders]

    if not user_product_ids:
        return {p.id: 0 for p in products}

    # Count products co-occurring with user's purchased products
    # Get all products from user's orders
    user_order_items = db.session.query(OrderItem).join(
        MerchantOrder, OrderItem.merchant_order_id == MerchantOrder.id
    ).join(
        OrderGroup, MerchantOrder.order_group_id == OrderGroup.id
    ).filter(
        OrderGroup.user_id == user_id
    ).all()

    # Group by order
    order_items_dict = {}
    for item in user_order_items:
        order_id = item.merchant_order_id
        if order_id not in order_items_dict:
            order_items_dict[order_id] = []
        order_items_dict[order_id].append(item.product_id)

    # Count co-occurrences
    co_purchase_counts = {}
    for order_id, product_ids in order_items_dict.items():
        # Products in the same order co-occur with each other
        for pid1 in product_ids:
            for pid2 in product_ids:
                if pid1 != pid2 and pid2 not in user_product_ids:
                    # Only count products the user has not purchased.
                    co_purchase_counts[pid2] = co_purchase_counts.get(
                        pid2, 0) + 1

    # Normalize scores
    max_count = max(co_purchase_counts.values()) if co_purchase_counts else 1
    for product in products:
        count = co_purchase_counts.get(product.id, 0)
        scores[product.id] = (count / max_count) * 100 if max_count > 0 else 0

    return scores


def calculate_popularity_score(products):
    scores = {}

    # Count sales (order count) for each product
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


def calculate_category_similarity_score(products, interest_category_ids):
    scores = {}

    if not interest_category_ids:
        return {p.id: 0 for p in products}

    for product in products:
        product_categories = [pc.category_id for pc in product.categories]
        if not product_categories:
            scores[product.id] = 0
            continue

        # Calculate Jaccard similarity
        intersection = len(set(product_categories) &
                           set(interest_category_ids))
        union = len(set(product_categories) | set(interest_category_ids))
        similarity = intersection / union if union > 0 else 0
        scores[product.id] = similarity * 100

    return scores


def get_product_recommendations(product_id, limit=6):
    try:
        product = Product.query.get_or_404(product_id)

        # Get product categories
        product_categories = [pc.category_id for pc in product.categories]

        # 1. Category similarity recommendations
        similar_products = Product.query.join(
            ProductCategory, Product.id == ProductCategory.product_id
        ).filter(
            ProductCategory.category_id.in_(product_categories),
            Product.id != product_id,
            Product.is_deleted.is_(False),
            Product.status == ProductStatus.ACTIVE
        ).distinct().limit(limit * 2).all()

        # 2. Co-purchase recommendations (simplified: return similar products)
        return similar_products[:limit]

    except Exception as e:
        logger.error(f"Product recommendation error: {e}", exc_info=True)
        return []
