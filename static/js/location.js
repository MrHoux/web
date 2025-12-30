/**
 * Location UI (Baidu Map JS API):
 * - Navbar city display (city-level)
 * - Map picker modal (search + click to pick)
 * - Browser geolocation -> reverse geocode -> fill province/city/district
 *
 * Stores location in localStorage:
 *   shopwave_location = { province, city, district, lat, lng, ts }
 */

const LS_KEY = 'shopwave_location';
function dbg() {}

function getConfig() {
    const ds = document.body?.dataset || {};
    const ak = ds.baiduAk || '';
    const v = ds.baiduJsV || '3.0';
    return {
        ak,
        v
    };
}

function readStoredLocation() {
    try {
        const raw = localStorage.getItem(LS_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (_) {
        return null;
    }
}

function storeLocation(loc) {
    try {
        localStorage.setItem(LS_KEY, JSON.stringify({ ...loc, ts: Date.now() }));
    } catch (_) {}
}

function setNavbarCityText(city) {
    const el = document.getElementById('nav-city');
    if (!el) return;
    el.textContent = city || 'Choose city';
}

function updateNavbarFromStorage() {
    const loc = readStoredLocation();
    setNavbarCityText(loc?.city || 'Choose city');
}

async function detectCityByIP() {
    await loadBaiduScript();
    return new Promise((resolve, reject) => {
        try {
            const lc = new BMap.LocalCity();
            lc.get((res) => {
                const name = res?.name || '';
                const center = res?.center;
                if (!name) return reject(new Error('No city'));
                resolve({
                    city: name,
                    lng: center?.lng,
                    lat: center?.lat
                });
            });
        } catch (e) {
            reject(e);
        }
    });
}

const LS_DENIED_KEY = 'shopwave_location_denied_at';
function recentlyDenied() {
    try {
        const ts = parseInt(localStorage.getItem(LS_DENIED_KEY) || '0');
        return Number.isFinite(ts) && ts > 0 && (Date.now() - ts) < (24 * 60 * 60 * 1000);
    } catch (_) {
        return false;
    }
}
function markDeniedNow() {
    try { localStorage.setItem(LS_DENIED_KEY, String(Date.now())); } catch (_) {}
}

let _baiduScriptPromise = null;
let _baiduLoadAttempt = 0;
function loadBaiduScript() {
    const { ak, v } = getConfig();
    if (!ak) return Promise.reject(new Error('Missing Baidu Map AK'));
    if (window.BMap) return Promise.resolve();
    if (_baiduScriptPromise) return _baiduScriptPromise;

    _baiduScriptPromise = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        _baiduLoadAttempt += 1;

        // Two URL forms seen in the wild. If one returns non-JS (e.g. AK/referrer error page),
        // onload still fires but window.BMap stays undefined. We'll retry once with the other.
        // Runtime evidence in this repo: /api endpoint can "load" but still leave BMap undefined.
        // Prefer /getscript first, fall back to /api.
        const useGetScript = _baiduLoadAttempt >= 1;
        const httpsParam = window.location.protocol === 'https:' ? '&https=1' : '';
        const src = useGetScript
            ? `https://api.map.baidu.com/getscript?v=${encodeURIComponent(v)}&ak=${encodeURIComponent(ak)}${httpsParam}`
            : `https://api.map.baidu.com/api?v=${encodeURIComponent(v)}&ak=${encodeURIComponent(ak)}${httpsParam}`;

        s.src = src;
        s.async = true;
        s.onload = () => {
            const check = () => {
                if (window.BMap) return resolve();

                // Retry once using alternative URL if first load didn't create BMap
                if (_baiduLoadAttempt < 2) {
                    try { s.remove(); } catch (_) {}
                    _baiduScriptPromise = null;
                    return loadBaiduScript().then(resolve).catch(reject);
                }
                reject(new Error('BMap not available after script load'));
            };

            // Microtask re-check (no setTimeout)
            Promise.resolve().then(check);
        };
        s.onerror = () => {
            reject(new Error('Failed to load Baidu Map JS API'));
        };
        document.head.appendChild(s);
    });
    return _baiduScriptPromise;
}

async function reverseGeocode(point) {
    await loadBaiduScript();
    return new Promise((resolve, reject) => {
        try {
            const geocoder = new BMap.Geocoder();
            geocoder.getLocation(point, (rs) => {
                if (!rs || !rs.addressComponents) return reject(new Error('No geocode result'));
                resolve(rs);
            });
        } catch (e) {
            reject(e);
        }
    });
}

async function gpsToBaiduPoint(lng, lat) {
    await loadBaiduScript();
    const pt = new BMap.Point(lng, lat);

    // Convert browser GPS(WGS84) to Baidu BD-09 when possible (improves accuracy in CN).
    // If conversion fails, fall back to raw point.
    if (!BMap.Convertor) return pt;
    const convertor = new BMap.Convertor();
    return new Promise((resolve) => {
        try {
            convertor.translate([pt], 1, 5, (data) => {
                if (data && data.status === 0 && data.points && data.points[0]) resolve(data.points[0]);
                else resolve(pt);
            });
        } catch (_) {
            resolve(pt);
        }
    });
}

function applyToAddressFields({ province, city, district }) {
    const provEl = document.getElementById('province');
    const cityEl = document.getElementById('city');
    const distEl = document.getElementById('district');
    const detailEl = document.getElementById('detail_address');

    if (provEl) {
        const tag = (provEl.tagName || '').toUpperCase();
        provEl.value = province || '';
    }
    if (cityEl) cityEl.value = city || '';
    if (distEl) distEl.value = district || '';
    // detail_address is optional; filled on confirm when we have a Baidu POI
    if (detailEl && detailEl.value === '' && false) {
        // placeholder to keep older callers safe; actual fill happens in commitSelection()
        detailEl.value = detailEl.value;
    }
}

async function useMyLocationAndFill() {
    if (!navigator.geolocation) throw new Error('Geolocation not supported');
    const pos = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 5 * 60 * 1000
        });
    });
    const lng = pos.coords.longitude;
    const lat = pos.coords.latitude;
    const bdPt = await gpsToBaiduPoint(lng, lat);
    const rs = await reverseGeocode(bdPt);
    const comp = rs.addressComponents;

    const loc = {
        province: comp.province || '',
        city: comp.city || '',
        district: comp.district || '',
        lng: bdPt.lng,
        lat: bdPt.lat
    };
    storeLocation(loc);
    updateNavbarFromStorage();
    applyToAddressFields(loc);
    return loc;
}

let _map = null;
let _marker = null;
let _modalHooked = false;
let _localSearch = null;
let _domClickHooked = false;
let _returnModalSelector = null;
let _mapA11yObserver = null;

// Pending selection state:
// - User may click/search many points, but we only commit to navbar/form on Confirm.
let _pending = null; // { pt, comp, address, pois: [{title,address,uid,point}], source }
let _selectedPoiIdx = -1;

function getPoiPanelEls() {
    return {
        panel: document.getElementById('baidu-poi-panel'),
        list: document.getElementById('baidu-poi-list'),
        selected: document.getElementById('baidu-poi-selected'),
        confirm: document.getElementById('btn-confirm-location'),
        hint: document.getElementById('baidu-location-hint')
    };
}

function safeText(s, maxLen = 120) {
    const t = String(s || '');
    return t.length > maxLen ? t.slice(0, maxLen - 1) + '…' : t;
}

function renderPoiPanel() {
    const { panel, list, selected, confirm } = getPoiPanelEls();
    if (!panel || !list || !selected || !confirm) return;

    const pois = _pending?.pois || [];
    if (!pois.length) {
        panel.style.display = 'none';
        list.innerHTML = '';
        selected.textContent = 'No place selected';
        confirm.disabled = true;
        return;
    }

    panel.style.display = '';
    list.innerHTML = pois.map((p, idx) => {
        const active = idx === _selectedPoiIdx;
        const title = safeText(p.title || 'Unknown place', 60);
        const addr = safeText(p.address || '', 80);
        return `
            <button type="button"
                class="list-group-item list-group-item-action d-flex justify-content-between align-items-start ${active ? 'active' : ''}"
                data-poi-idx="${idx}">
                <div class="me-3">
                    <div class="fw-semibold">${title}</div>
                    <div class="small ${active ? 'text-white-50' : 'text-secondary'}">${addr}</div>
                </div>
                <div class="small ${active ? 'text-white-50' : 'text-secondary'}">Select</div>
            </button>
        `;
    }).join('');

    const chosen = pois[_selectedPoiIdx];
    selected.textContent = chosen?.title ? safeText(chosen.title, 40) : 'No place selected';
    confirm.disabled = !chosen;
}

function setPendingSelection({ pt, rs, source, searchResults }) {
    const comp = rs?.addressComponents || {};
    const addr = rs?.address || '';

    // 1) Prefer reverseGeocode surroundingPois (nearby, stable, "searchable places")
    const fromSurrounding = Array.isArray(rs?.surroundingPois)
        ? rs.surroundingPois
        : [];

    // 2) If selection came from LocalSearch, use top results as candidates
    const fromSearch = Array.isArray(searchResults) ? searchResults : [];

    const rawPois = (fromSearch.length ? fromSearch : fromSurrounding).slice(0, 6);
    const pois = rawPois.map((p) => ({
        title: p?.title || p?.name || '',
        address: p?.address || '',
        uid: p?.uid || p?.id || '',
        point: p?.point || pt
    })).filter(p => !!p.title && !!p.point);

    _pending = {
        pt,
        comp: {
            province: comp.province || '',
            city: comp.city || '',
            district: comp.district || ''
        },
        address: addr,
        pois,
        source: source || 'unknown'
    };

    _selectedPoiIdx = pois.length ? 0 : -1;
    renderPoiPanel();
}

function clearPendingSelection(reason) {
    _pending = null;
    _selectedPoiIdx = -1;
    renderPoiPanel();
}

function commitSelection() {
    const chosen = _pending?.pois?.[_selectedPoiIdx];
    const pt = chosen?.point || _pending?.pt;
    const comp = _pending?.comp || {};
    if (!chosen || !pt) {
        // #region agent log
        dbg('H10', 'confirm blocked (no selected poi)', { has_pending: !!_pending, idx: _selectedPoiIdx });
        // #endregion
        return false;
    }

    const loc = {
        province: comp.province || '',
        city: comp.city || '',
        district: comp.district || '',
        lng: pt.lng,
        lat: pt.lat,
        // optional extras for future server-side validation
        baidu_poi_uid: chosen.uid || '',
        baidu_poi_title: chosen.title || ''
    };

    storeLocation(loc);
    updateNavbarFromStorage();
    applyToAddressFields(loc);

    // Fill "detail_address" as fine-grained as possible: POI title + POI address
    const detailEl = document.getElementById('detail_address');
    if (detailEl) {
        const title = String(chosen.title || '').trim();
        const addr = String(chosen.address || '').trim();
        const composed = [title, addr].filter(Boolean).join(' · ');
        if (composed) detailEl.value = composed;
    }

    // Close modal after user confirms selection (UX: confirm implies done editing).
    try {
        const modalEl = document.getElementById('locationModal');
        const hasBootstrap = !!window.bootstrap?.Modal;
        if (modalEl && hasBootstrap) {
            const inst = window.bootstrap.Modal.getInstance(modalEl) || new window.bootstrap.Modal(modalEl);
            inst.hide();
        }
    } catch (e) {
    }

    // Return to the originating modal if requested (e.g. address form).
    if (_returnModalSelector) {
        try {
            const modalEl = document.getElementById('locationModal');
            const returnEl = document.querySelector(_returnModalSelector);
            const hasBootstrap = !!window.bootstrap?.Modal;
            const showReturn = () => {
                if (!returnEl || !hasBootstrap) return;
                const inst = window.bootstrap.Modal.getInstance(returnEl) || new window.bootstrap.Modal(returnEl);
                inst.show();
            };
            if (modalEl) {
                modalEl.addEventListener('hidden.bs.modal', showReturn, { once: true });
            } else {
                showReturn();
            }
        } catch (_) {
        }
    }

    return true;
}

function ensureMarker(pt) {
    if (!_map) return;
    if (_marker) _map.removeOverlay(_marker);
    _marker = new BMap.Marker(pt);
    _map.addOverlay(_marker);
}

function normalizeMapA11y(root) {
    if (!root) return;
    const imgs = root.querySelectorAll('img');
    imgs.forEach((img) => {
        const link = img.closest('a');
        const linkLabel = link?.getAttribute('aria-label') || link?.getAttribute('title') || '';
        if (!img.hasAttribute('alt')) {
            img.setAttribute('alt', link ? (linkLabel || 'Baidu map') : '');
        }
        if (!link) img.setAttribute('role', 'presentation');
    });

    const links = root.querySelectorAll('a');
    links.forEach((link) => {
        const hasText = (link.textContent || '').trim().length > 0;
        const hasLabel = link.getAttribute('aria-label') || link.getAttribute('title');
        if (!hasText && !hasLabel) {
            link.setAttribute('aria-label', 'Baidu map');
        }
    });
}

function setupMapA11y() {
    const mapEl = document.getElementById('baidu-map');
    if (!mapEl) return;
    normalizeMapA11y(mapEl);
    if (_mapA11yObserver) return;
    _mapA11yObserver = new MutationObserver((mutations) => {
        mutations.forEach((m) => {
            m.addedNodes.forEach((node) => {
                if (!node || node.nodeType !== 1) return;
                normalizeMapA11y(node);
            });
        });
    });
    _mapA11yObserver.observe(mapEl, { childList: true, subtree: true });
}

async function initLocationModal() {
    const modalEl = document.getElementById('locationModal');
    const mapEl = document.getElementById('baidu-map');
    if (!modalEl || !mapEl) return;

    await loadBaiduScript();

    const ensureMap = () => {
        if (_map) return;
        _map = new BMap.Map('baidu-map');
        const defaultPt = new BMap.Point(116.404, 39.915); // Beijing fallback
        _map.centerAndZoom(defaultPt, 12);
        _map.enableScrollWheelZoom(true);
        _map.addControl(new BMap.NavigationControl());
        _map.addControl(new BMap.ScaleControl());
        setupMapA11y();

        _map.addEventListener('click', async (e) => {
            const pt = e.point;
            ensureMarker(pt);
            try {
                const rs = await reverseGeocode(pt);
                setPendingSelection({ pt, rs, source: 'map_click' });
            } catch (_) {}
        });

        // DOM click fallback: in some environments BMap click event may not fire reliably.
        if (!_domClickHooked) {
            _domClickHooked = true;
            mapEl.addEventListener('click', async (ev) => {
                try {
                    if (!_map || !BMap || !BMap.Pixel) return;
                    const rect = mapEl.getBoundingClientRect();
                    const x = ev.clientX - rect.left;
                    const y = ev.clientY - rect.top;
                    const pt = _map.pixelToPoint(new BMap.Pixel(x, y));
                    if (!pt) return;
                    ensureMarker(pt);
                    const rs = await reverseGeocode(pt);
                    setPendingSelection({ pt, rs, source: 'dom_click' });
                } catch (_) {}
            }, { passive: true });
        }

        // Autocomplete + search
        const input = document.getElementById('baidu-place-input');
        if (input) {
            const ac = new BMap.Autocomplete({ input: 'baidu-place-input', location: _map });
            ac.addEventListener('onconfirm', (e) => {
                const v = e.item?.value;
                const kw = v ? `${v.province || ''}${v.city || ''}${v.district || ''}${v.street || ''}${v.business || ''}` : input.value;
                if (!_localSearch) {
                    _localSearch = new BMap.LocalSearch(_map, {
                        onSearchComplete: async function () {
                            try {
                                const r = _localSearch.getResults();
                                const top = [];
                                for (let i = 0; i < Math.min(6, r?.getNumPois?.() || 0); i++) {
                                    const poi = r.getPoi(i);
                                    if (poi) top.push(poi);
                                }
                                const poi0 = top[0];
                                const p = poi0?.point;
                                if (!p) return;
                                _map.centerAndZoom(p, 15);
                                ensureMarker(p);
                                const rs = await reverseGeocode(p);
                                setPendingSelection({ pt: p, rs, source: 'search_autocomplete', searchResults: top });
                            } catch (e2) {
                            }
                        }
                    });
                }
                _localSearch.search(kw);
            });

            // Enter-to-search fallback (in case autocomplete dropdown is blocked)
            input.addEventListener('keydown', (ev) => {
                if (ev.key !== 'Enter') return;
                ev.preventDefault();
                const kw = (input.value || '').trim();
                if (!kw) return;
                if (!_localSearch) {
                    _localSearch = new BMap.LocalSearch(_map, {
                        onSearchComplete: async function () {
                            try {
                                const r = _localSearch.getResults();
                                const top = [];
                                for (let i = 0; i < Math.min(6, r?.getNumPois?.() || 0); i++) {
                                    const poi = r.getPoi(i);
                                    if (poi) top.push(poi);
                                }
                                const poi0 = top[0];
                                const p = poi0?.point;
                                if (!p) return;
                                _map.centerAndZoom(p, 15);
                                ensureMarker(p);
                                const rs = await reverseGeocode(p);
                                setPendingSelection({ pt: p, rs, source: 'search_enter', searchResults: top });
                            } catch (e2) {
                            }
                        }
                    });
                }
                _localSearch.search(kw);
            });
        }
    };

    // restore from storage when opening modal
    if (!_modalHooked) {
        _modalHooked = true;
        modalEl.addEventListener('show.bs.modal', (ev) => {
            const trigger = ev.relatedTarget;
            const selector = trigger?.getAttribute?.('data-return-modal');
            _returnModalSelector = selector || null;
        });
        modalEl.addEventListener('shown.bs.modal', () => {
            ensureMap();
            setupMapA11y();
            try {
                // Ensure proper render after being shown (bootstrap modal was hidden before)
                _map && _map.checkResize && _map.checkResize();
            } catch (_) {}

            const loc = readStoredLocation();
            if (loc && _map) {
                const pt = new BMap.Point(loc.lng, loc.lat);
                _map.centerAndZoom(pt, 13);
                ensureMarker(pt);
            }

            // reset pending UI each time modal opens
            clearPendingSelection('modal_shown');
        });

        modalEl.addEventListener('hidden.bs.modal', () => {
            clearPendingSelection('modal_hidden');
            _returnModalSelector = null;
        });
    }

    // (No extra shown handler here; we already handle restore inside the single hooked handler.)

    // buttons
    document.getElementById('btn-use-my-location')?.addEventListener('click', async () => {
        try {
            if (!navigator.geolocation) throw new Error('Geolocation not supported');
            const pos = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 5 * 60 * 1000
                });
            });
            const bdPt = await gpsToBaiduPoint(pos.coords.longitude, pos.coords.latitude);
            const rs = await reverseGeocode(bdPt);
            if (_map) {
                _map.centerAndZoom(bdPt, 13);
                ensureMarker(bdPt);
            }
            setPendingSelection({ pt: bdPt, rs, source: 'use_my_location' });
        } catch (_) {}
    });

    document.getElementById('btn-clear-location')?.addEventListener('click', () => {
        try { localStorage.removeItem(LS_KEY); } catch (_) {}
        updateNavbarFromStorage();
        clearPendingSelection('clear_clicked');
    });

    // POI list selection + confirm
    const { list, confirm, hint } = getPoiPanelEls();
    list?.addEventListener('click', (ev) => {
        const btn = ev.target?.closest?.('[data-poi-idx]');
        if (!btn) return;
        const idx = parseInt(btn.getAttribute('data-poi-idx') || '-1', 10);
        if (!Number.isFinite(idx) || idx < 0) return;
        _selectedPoiIdx = idx;
        renderPoiPanel();
    });

    confirm?.addEventListener('click', () => {
        const ok = commitSelection();
        if (hint) {
            hint.textContent = ok
                ? 'Location confirmed.'
                : 'Please select a recommended place (Baidu searchable POI), then Confirm.';
        }
    });
}

export async function initLocationUI() {
    updateNavbarFromStorage();
    // If no stored city, request real browser geolocation (user permission required).
    // This produces a real city from reverse geocoding, not an IP guess.
    const existing = readStoredLocation();
    if (!existing?.city && !recentlyDenied()) {
        setNavbarCityText('Locating…');
        try {
            await useMyLocationAndFill();
        } catch (_) {
            markDeniedNow();
            // Fallback: IP-based city inference (city-level only)
            try {
                const cityInfo = await detectCityByIP();
                const loc = {
                    province: existing?.province || '',
                    city: cityInfo.city || '',
                    district: existing?.district || '',
                    lng: cityInfo.lng,
                    lat: cityInfo.lat
                };
                storeLocation(loc);
                updateNavbarFromStorage();
            } catch (e2) {
                setNavbarCityText('Choose city');
            }
        }
    }
    // Init modal lazily (but attach once DOM is ready)
    try {
        await initLocationModal();
    } catch (_) {
        // If AK missing or script fails, keep UI minimal.
        setNavbarCityText('Choose city');
    }

    // Expose a helper for pages that want "Use my location" without opening modal
    window.ShopWave = window.ShopWave || {};
    window.ShopWave.useMyLocationAndFill = useMyLocationAndFill;
}
