/**
 * Wishlist UI helpers: sync heart button state and toggle silently.
 */

export async function fetchWishlistSet(api) {
    try {
        const data = await api.get('/api/wishlist', { showLoading: false });
        return new Set((data.product_ids || []).map(x => parseInt(x)));
    } catch (_) {
        return new Set();
    }
}

export function applyWishlistButtonState(btn, inWishlist) {
    const icon = btn?.querySelector?.('i');
    if (!icon) return;
    if (inWishlist) {
        icon.classList.remove('bi-heart');
        icon.classList.add('bi-heart-fill', 'text-danger');
        btn.dataset.inWishlist = '1';
    } else {
        icon.classList.remove('bi-heart-fill', 'text-danger');
        icon.classList.add('bi-heart');
        btn.dataset.inWishlist = '0';
    }
}

export async function initWishlistButtons(buttons, api, { animateHeart } = {}) {
    const btns = Array.from(buttons || []);
    if (!btns.length) return;

    const set = await fetchWishlistSet(api);
    btns.forEach(btn => {
        const pid = parseInt(btn.dataset.productId);
        if (!Number.isFinite(pid)) return;
        applyWishlistButtonState(btn, set.has(pid));
    });

    btns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const pid = parseInt(btn.dataset.productId);
            if (!Number.isFinite(pid)) return;

            if (typeof animateHeart === 'function') {
                try { animateHeart(btn); } catch (_) {}
            }

            try {
                const res = await api.post('/api/wishlist/toggle', { product_id: pid }, { showLoading: false });
                applyWishlistButtonState(btn, !!res.in_wishlist);
            } catch (_) {
                // Silent by design
            }
        });
    });
}


