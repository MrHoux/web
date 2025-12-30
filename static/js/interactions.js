/**
 * Enhances UI with animations and interactions
 */

export function initInteractions() {
    initScrollReveal();
    initNavbarScroll();
    initActiveNav();
    initScrollTop();
}

/**
 * Reveal elements as they scroll into view
 */
function initScrollReveal() {
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target); // Only animate once
            }
        });
    }, observerOptions);

    // Target product cards and feature sections
    const targets = document.querySelectorAll('.product-card, .hero-section, section h2, .col-md-4');
    targets.forEach((el, index) => {
        el.classList.add('reveal-on-scroll');
        // Add staggered delay to grid items based on their index
        if (el.classList.contains('product-card')) {
            const delay = (index % 4) * 100; // 0, 100, 200, 300ms
            el.style.transitionDelay = `${delay}ms`;
        }
        observer.observe(el);
    });
}

/**
 * Navbar transformation on scroll
 */
function initNavbarScroll() {
    const navbar = document.querySelector('.navbar');
    
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    });
}

/**
 * Highlight current page nav link
 */
function initActiveNav() {
    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    document.querySelectorAll('.navbar .nav-link').forEach(link => {
        try {
            const href = (link.getAttribute('href') || '').trim();
            if (!href || href === '#') return;
            const url = new URL(href, window.location.origin);
            const linkPath = url.pathname.replace(/\/+$/, '') || '/';
            if (linkPath === path) {
                link.classList.add('active');
            }
        } catch (e) {
            // ignore invalid hrefs
        }
    });
}

/**
 * Scroll-to-top floating button
 */
function initScrollTop() {
    const btn = document.getElementById('scroll-top');
    if (!btn) return;

    const onScroll = () => {
        if (window.scrollY > 400) btn.classList.add('is-visible');
        else btn.classList.remove('is-visible');
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    btn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

/**
 * Add visual feedback helper for buttons
 * usage: await animateButton(btn, 'success', '<i class="bi bi-check2"></i> Added');
 */
export function animateButton(btnElement, type = 'success', tempText = null) {
    return new Promise(resolve => {
        const originalHtml = btnElement.innerHTML;
        const originalClasses = btnElement.className;
        const width = btnElement.offsetWidth;

        // Fix width to prevent jumping
        btnElement.style.width = `${width}px`;
        
        // Change state
        if (type === 'success') {
            btnElement.classList.remove('btn-primary', 'btn-outline-primary');
            btnElement.classList.add('btn-success-state');
            if (tempText) btnElement.innerHTML = tempText;
        }

        // Revert after delay
        setTimeout(() => {
            btnElement.className = originalClasses;
            btnElement.innerHTML = originalHtml;
            btnElement.style.width = '';
            resolve();
        }, 2000);
    });
}

/**
 * Animate wishlist heart
 */
export function animateHeart(btnElement) {
    const icon = btnElement.querySelector('i');
    icon.classList.add('animate-pop');
    setTimeout(() => icon.classList.remove('animate-pop'), 300);
}

