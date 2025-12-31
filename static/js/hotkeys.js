const HOTKEY_SELECTOR = [
    '[data-hotkey]',
    'button',
    'a[href]',
    '[role="button"]',
    'input[type="button"]',
    'input[type="submit"]',
    'input[type="reset"]'
].join(',');

const KEY_POOL = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');

let hotkeyMap = new Map();
let initialized = false;
let scheduled = false;
let observer = null;

function normalizeKey(raw) {
    const key = String(raw || '').trim().toUpperCase();
    if (!key) return '';
    return /^[A-Z0-9]$/.test(key) ? key : '';
}

function isInteractive(el) {
    if (!el) return false;
    if (el.closest('[data-hotkey-ignore="1"]')) return false;
    if (el.hasAttribute('disabled')) return false;
    if (el.getAttribute('aria-disabled') === 'true') return false;
    if (el.tabIndex < 0) return false;
    return true;
}

function isVisible(el) {
    if (!el) return false;
    if (el.offsetParent !== null) return true;
    return el.getClientRects().length > 0;
}

function getLabel(el) {
    return (
        el.getAttribute('data-hotkey-label') ||
        el.getAttribute('aria-label') ||
        el.getAttribute('title') ||
        el.textContent ||
        ''
    );
}

function pickKeyFromLabel(label, used) {
    const chars = String(label || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    for (const ch of chars) {
        if (!used.has(ch)) return ch;
    }
    return '';
}

function applyKey(el, key, isAuto) {
    if (!key) return false;
    el.setAttribute('aria-keyshortcuts', `Alt+Shift+${key}`);
    if (!el.getAttribute('data-hotkey')) {
        el.setAttribute('data-hotkey', key);
    }
    if (isAuto) {
        el.setAttribute('data-hotkey-auto', '1');
    }
    return true;
}

function buildHotkeys() {
    const elements = Array.from(document.querySelectorAll(HOTKEY_SELECTOR))
        .filter(isInteractive)
        .filter(isVisible);

    const used = new Set();
    const nextMap = new Map();

    // Pass 1: honor explicit data-hotkey
    elements.forEach((el) => {
        const raw = el.getAttribute('data-hotkey');
        const key = normalizeKey(raw);
        if (!key || used.has(key)) return;
        used.add(key);
        nextMap.set(key, el);
        applyKey(el, key, false);
    });

    // Pass 2: auto-assign from label, then from pool
    elements.forEach((el) => {
        const existing = el.getAttribute('data-hotkey');
        const normalized = normalizeKey(existing);
        if (normalized && used.has(normalized)) {
            return;
        }
        if (normalized && !used.has(normalized)) {
            used.add(normalized);
            nextMap.set(normalized, el);
            applyKey(el, normalized, false);
            return;
        }

        let key = pickKeyFromLabel(getLabel(el), used);
        if (!key) {
            key = KEY_POOL.find(k => !used.has(k)) || '';
        }
        if (!key) return;
        used.add(key);
        nextMap.set(key, el);
        applyKey(el, key, true);
    });

    hotkeyMap = nextMap;
}

function scheduleRefresh() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
        scheduled = false;
        buildHotkeys();
    });
}

function handleKeydown(ev) {
    if (!ev.altKey || ev.ctrlKey || ev.metaKey) return;

    const key = normalizeKey(ev.key);
    const isAltShift = ev.shiftKey;

    // Block browser Alt / Alt+Shift shortcuts
    ev.preventDefault();
    ev.stopPropagation();

    if (!isAltShift || !key) return;
    const target = hotkeyMap.get(key);
    if (!target) return;
    target.click();
}

function setupObservers() {
    if (observer) return;
    observer = new MutationObserver(() => scheduleRefresh());
    observer.observe(document.body, { childList: true, subtree: true });
}

export function initHotkeys() {
    if (initialized) return;
    initialized = true;
    buildHotkeys();
    document.addEventListener('keydown', handleKeydown, true);
    document.addEventListener('shown.bs.modal', scheduleRefresh);
    document.addEventListener('shown.bs.offcanvas', scheduleRefresh);
    window.addEventListener('resize', scheduleRefresh);
    setupObservers();
    window.NovaMartHotkeys = {
        refresh: buildHotkeys
    };
}
