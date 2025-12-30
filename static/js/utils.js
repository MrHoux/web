/**
 * Utility functions
 */

// Format currency
export function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD' // Can be changed based on requirement
    }).format(amount);
}

// Format date
export function formatDate(dateString, options = {}) {
    if (!dateString) return '';
    // Server timestamps are stored as UTC but often serialized without timezone ("YYYY-MM-DDTHH:mm:ss").
    // Interpret timezone-less strings as UTC, then format in UTC+8 (Asia/Shanghai).
    const s = String(dateString);
    const hasTz = /([zZ]|[+-]\d\d:\d\d)$/.test(s);
    const d = new Date(hasTz ? s : (s + 'Z'));
    if (Number.isNaN(d.getTime())) return s;
    const withSeconds = options.withSeconds !== false;
    const formatOptions = {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    };
    if (withSeconds) {
        formatOptions.second = '2-digit';
    }
    return new Intl.DateTimeFormat('zh-CN', formatOptions).format(d);
}

// Show toast notification
export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container || !window.bootstrap || !bootstrap.Toast) return;

    const map = {
        success: 'text-bg-success',
        error: 'text-bg-danger',
        danger: 'text-bg-danger',
        warning: 'text-bg-warning',
        info: 'text-bg-dark'
    };
    const cls = map[type] || map.info;

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center ${cls} border-0 shadow`;
    toastEl.role = 'alert';
    toastEl.ariaLive = 'assertive';
    toastEl.ariaAtomic = 'true';

    const d = document.createElement('div');
    d.className = 'd-flex';

    const body = document.createElement('div');
    body.className = 'toast-body';
    body.textContent = String(message ?? '');

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-close btn-close-white me-2 m-auto';
    btn.setAttribute('data-bs-dismiss', 'toast');
    btn.setAttribute('aria-label', 'Close');

    d.appendChild(body);
    d.appendChild(btn);
    toastEl.appendChild(d);
    container.appendChild(toastEl);

    const t = new bootstrap.Toast(toastEl, { delay: 3000 });
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove(), { once: true });
    t.show();
}

// Debounce function for search inputs
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Update cart badge
export function updateCartBadge(count) {
    const badge = document.getElementById('cart-badge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'block' : 'none';
    }
}
