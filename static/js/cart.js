// Cart Logic
import { api } from './api.js';
import { showToast } from './utils.js';

export async function initCart() {
    updateCartBadge();
}

export async function updateCartBadge() {
    const badge = document.getElementById('cart-badge');
    if (!badge) return;

    try {
        const data = await api.get('/cart');
        if (data.total_items > 0) {
            badge.textContent = data.total_items;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }
    } catch (error) {
        // Silent error for cart badge
        console.warn('Failed to update cart badge:', error);
    }
}

export async function addToCart(productId, quantity = 1) {
    try {
        await api.post('/api/cart/items', { product_id: productId, quantity });
        showToast('Added to cart successfully!', 'success');
        updateCartBadge();
        return true;
    } catch (error) {
        showToast(error.message, 'error');
        return false;
    }
}

