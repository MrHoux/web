import { api } from './api.js';
import { updateCartBadge, showToast } from './utils.js';
import { initInteractions } from './interactions.js';
import { initLocationUI } from './location.js';

// Build APP_CONFIG from server-rendered data-* attributes (avoids templating inside JS)
if (!window.APP_CONFIG) {
    const ds = document.body?.dataset || {};
    const isAuthenticated = ds.auth === '1';
    const userId = ds.userId ? Number(ds.userId) : null;
    window.APP_CONFIG = {
        currentUser: {
            isAuthenticated,
            role: ds.role || '',
            id: Number.isFinite(userId) ? userId : null
        },
        urls: {
            cart: {
                get: ds.cartGet || '/cart',
                add: '/api/cart/items',
                update: '/api/cart/items/',
                remove: '/api/cart/items/'
            }
        }
    };
}

/**
 * Main application initialization
 */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize animations and interactions
    initInteractions();
    initLocationUI();

    // Render server-side flash() messages as toasts (no layout shift)
    try {
        const el = document.getElementById('flash-messages');
        const raw = el?.textContent || '[]';
        const flashes = JSON.parse(raw);
        if (Array.isArray(flashes)) {
            flashes.forEach(([category, message]) => {
                const t = category === 'error' ? 'error' : (category || 'info');
                showToast(message, t);
            });
        }
    } catch (e) {
        // ignore
    }

    /**
     * Bootstrap modal safety:
     * If a modal is rendered inside an element that animates with transform (e.g. .animate-fade-in),
     * it can end up behind the backdrop (page looks greyed out and unclickable).
     * Fix: move all modals to <body> so they participate in the top-level stacking context.
     */
    try {
        document.querySelectorAll('.modal').forEach(m => {
            if (m.parentElement !== document.body) document.body.appendChild(m);
        });
    } catch (e) {
        // ignore
    }

    // Cleanup orphan backdrops if something goes wrong
    const cleanupBackdrops = () => {
        try {
            if (!document.querySelector('.modal.show')) {
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.removeProperty('padding-right');
            }
        } catch (e) {
            // ignore
        }
    };
    document.addEventListener('hidden.bs.modal', cleanupBackdrops);
    window.addEventListener('popstate', cleanupBackdrops);
    window.addEventListener('hashchange', cleanupBackdrops);

    // Initialize tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // Initialize cart badge if logged in as CUSTOMER
    if (window.APP_CONFIG.currentUser.isAuthenticated && 
        window.APP_CONFIG.currentUser.role === 'CUSTOMER') {
        initCartBadge();
    }

    // Basic client-side search sanitization (complements backend ORM safety).
    document.querySelectorAll('form[data-search-form="1"]').forEach(form => {
        form.addEventListener('submit', () => {
            const input = form.querySelector('[data-search-input="1"]');
            if (!input) return;
            input.value = sanitizeSearchInput(input.value);
        });
    });
});

function sanitizeSearchInput(value) {
    const raw = String(value || '');
    const trimmed = raw.slice(0, 80);
    return trimmed
        .replace(/\u0000/g, '')
        .replace(/--|\/\*|\*\/|;|['"`\\#]/g, ' ')
        .replace(/\\s+/g, ' ')
        .trim();
}

async function initCartBadge() {
    try {
        const data = await api.get(window.APP_CONFIG.urls.cart.get);
        updateCartBadge(data.total_items || 0);
    } catch (error) {
        console.error('Failed to load cart count:', error);
    }
}

// Export for global access if needed
window.ShopWave = window.ShopWave || {};
window.ShopWave.showToast = showToast;
window.ShopWave.openSupportChat = () => {
    window.location.href = '/support/chat';
};
window.ShopWave.openMerchantChat = (merchantId) => {
    if (!merchantId) return;
    window.location.href = `/support/chat?merchant_id=${encodeURIComponent(merchantId)}`;
};
