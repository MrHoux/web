import { api } from './api.js';
import { showToast, formatDate } from './utils.js';

const root = document.getElementById('chat-root');
if (root) {
    const role = (root.dataset.role || 'customer').toLowerCase();
    const startMerchantId = parseInt(root.dataset.startMerchantId || '', 10);

    const state = {
        conversations: [],
        activeId: null,
        lastMessageId: 0,
        pollTimer: null,
        listTimer: null,
        filterTerm: ''
    };

    const emptyState = {
        label: 'Please select a conversation',
        sub: 'Choose a conversation on the left to get started.'
    };

    const els = {
        convList: document.getElementById('chat-conv-list'),
        messages: document.getElementById('chat-messages'),
        peerLabel: document.getElementById('chat-peer-label'),
        peerSub: document.getElementById('chat-peer-sub'),
        input: document.getElementById('chat-input'),
        sendBtn: document.getElementById('chat-send-btn'),
        emojiBtn: document.getElementById('chat-emoji-btn'),
        emojiPanel: document.getElementById('chat-emoji-panel'),
        imageInput: document.getElementById('chat-image-input'),
        productBtn: document.getElementById('chat-product-btn'),
        search: document.getElementById('chat-search'),
        backBtn: document.querySelector('.chat-back-btn')
    };

    const compactQuery = window.matchMedia('(max-width: 767.98px)');

    const endpoints = {
        customer: {
            list: '/api/chat/conversations',
            startAdmin: '/api/chat/admin/start',
            startMerchant: '/api/chat/merchant/start'
        },
        admin: {
            list: '/api/chat/admin/conversations'
        },
        merchant: {
            list: '/api/chat/merchant/conversations'
        }
    };

    initChat();

    async function initChat() {
        bindComposer();
        bindSearch();
        bindCompactLayout();
        renderEmojiPanel();
        updateProductButton();

        if (role === 'customer') {
            await ensureCustomerConversation();
        }
        await loadConversations();

        state.listTimer = setInterval(loadConversations, 8000);
        if (document.hidden !== undefined) {
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) {
                    updateProductButton();
                    loadConversations();
                    if (state.activeId) loadMessages(state.activeId, { reset: true });
                }
            });
        }
    }

    function bindCompactLayout() {
        applyCompactLayout();
        if (compactQuery.addEventListener) {
            compactQuery.addEventListener('change', applyCompactLayout);
        } else if (compactQuery.addListener) {
            compactQuery.addListener(applyCompactLayout);
        }
        if (els.backBtn) {
            els.backBtn.addEventListener('click', () => {
                if (!compactQuery.matches) return;
                root.classList.remove('chat-show-main');
            });
        }
    }

    function applyCompactLayout() {
        if (!root) return;
        if (compactQuery.matches) {
            root.classList.add('chat-compact');
            if (!state.activeId) {
                root.classList.remove('chat-show-main');
            }
        } else {
            root.classList.remove('chat-compact', 'chat-show-main');
        }
    }

    function bindSearch() {
        if (!els.search) return;
        els.search.addEventListener('input', () => {
            state.filterTerm = (els.search.value || '').trim().toLowerCase();
            renderConversationList();
        });
    }

    async function ensureCustomerConversation() {
        try {
            if (Number.isFinite(startMerchantId)) {
                const res = await api.post(endpoints.customer.startMerchant, { merchant_id: startMerchantId }, { showLoading: true });
                state.activeId = res.conversation_id;
            } else {
                const res = await api.post(endpoints.customer.startAdmin, {}, { showLoading: true });
                state.activeId = res.conversation_id;
            }
        } catch (e) {
            showToast(e.message || 'Failed to start chat', 'error');
        }
    }

    async function loadConversations() {
        try {
            const listUrl = endpoints[role]?.list;
            if (!listUrl) return;
            const res = await api.get(listUrl, { showLoading: false });
            state.conversations = res.items || [];
            renderConversationList();
        } catch (e) {
            if (els.convList) {
                els.convList.innerHTML = '<div class="text-center text-secondary py-5">Failed to load.</div>';
            }
            if (!state.activeId) {
                setEmptyState();
            }
        }
    }

    function renderConversationList() {
        const items = state.filterTerm
            ? state.conversations.filter(c => {
                const label = (c.peer?.label || '').toLowerCase();
                const last = (c.last_message || '').toLowerCase();
                return `${label} ${last}`.includes(state.filterTerm);
            })
            : state.conversations;
        if (!els.convList) return;

        if (!items.length) {
            const msg = state.filterTerm ? 'No matches found.' : 'No conversations yet.';
            els.convList.innerHTML = `<div class="text-center text-secondary py-5">${msg}</div>`;
            if (!state.activeId) {
                setEmptyState();
            }
            return;
        }

        const html = items.map(c => {
            const unread = c.unread_count || 0;
            const lastLabel = c.last_message_type === 'PRODUCT_LINK'
                ? 'Product link'
                : (c.last_message || '');
            const avatar = (c.peer?.label || 'C').trim().charAt(0).toUpperCase();
            return `
                <div class="chat-list-item ${state.activeId === c.id ? 'active' : ''}" data-id="${c.id}">
                    <div class="chat-avatar">${escapeHtml(avatar)}</div>
                    <div class="chat-list-text">
                        <div class="fw-semibold">${escapeHtml(c.peer?.label || 'Conversation')}</div>
                        <div class="small text-secondary text-truncate">${escapeHtml(lastLabel)}</div>
                    </div>
                    ${unread ? `<span class="chat-unread-badge">${unread}</span>` : ''}
                </div>
            `;
        }).join('');

        els.convList.innerHTML = html;
        els.convList.querySelectorAll('.chat-list-item').forEach(item => {
            item.addEventListener('click', () => {
                const id = parseInt(item.dataset.id, 10);
                if (Number.isFinite(id)) {
                    selectConversation(id);
                }
            });
        });

        if (state.activeId) {
            const active = state.conversations.find(i => i.id === state.activeId);
            if (active) {
                updatePeerHeader(active);
            } else {
                state.activeId = null;
                setEmptyState();
            }
        } else {
            setEmptyState();
        }
    }

    async function selectConversation(id) {
        state.activeId = id;
        state.lastMessageId = 0;
        updatePeerHeader(state.conversations.find(c => c.id === id));
        await loadMessages(id, { reset: true });
        markRead(id);
        setupPolling();
        renderConversationList();
        if (compactQuery.matches) {
            root.classList.add('chat-show-main');
        }
    }

    function updatePeerHeader(conv) {
        if (!conv) return;
        if (els.peerLabel) els.peerLabel.textContent = conv.peer?.label || 'Conversation';
        if (els.peerSub) {
            const subtitle = conv.type === 'CUSTOMER_ADMIN'
                ? 'Support will reply here.'
                : 'Merchant chat for product and order questions.';
            els.peerSub.textContent = subtitle;
        }
    }

    function setEmptyState() {
        if (els.peerLabel) els.peerLabel.textContent = emptyState.label;
        if (els.peerSub) els.peerSub.textContent = emptyState.sub;
        if (els.messages) {
            els.messages.innerHTML = `<div class="text-center text-secondary py-5 chat-empty">${emptyState.label}</div>`;
        }
    }

    async function loadMessages(conversationId, { reset } = { reset: true }) {
        try {
            const res = await api.get(`/api/chat/conversations/${conversationId}/messages`, { showLoading: false });
            const items = res.items || [];
            if (reset) {
                renderMessages(items);
            } else {
                appendMessages(items);
            }
            if (items.length) {
                state.lastMessageId = items[items.length - 1].id;
            }
            scrollToBottom();
        } catch (e) {
            if (els.messages) {
                els.messages.innerHTML = '<div class="text-center text-secondary py-5">Failed to load messages.</div>';
            }
        }
    }

    async function pollNewMessages() {
        if (!state.activeId) return;
        try {
            const res = await api.get(`/api/chat/conversations/${state.activeId}/messages?after_id=${state.lastMessageId || 0}`, { showLoading: false });
            const items = res.items || [];
            if (items.length) {
                appendMessages(items);
                state.lastMessageId = items[items.length - 1].id;
                scrollToBottom();
                markRead(state.activeId);
                loadConversations();
            }
        } catch (e) {
            // silent
        }
    }

    function setupPolling() {
        if (state.pollTimer) clearInterval(state.pollTimer);
        state.pollTimer = setInterval(pollNewMessages, 4000);
    }

    function renderMessages(items) {
        if (!els.messages) return;
        if (!items.length) {
            els.messages.innerHTML = '<div class="text-center text-secondary py-5 chat-empty">No messages yet.</div>';
            return;
        }
        els.messages.innerHTML = '';
        items.forEach(item => els.messages.appendChild(buildMessageNode(item)));
    }

    function appendMessages(items) {
        if (!els.messages || !items.length) return;
        if (els.messages.querySelector('.chat-empty')) {
            els.messages.innerHTML = '';
        }
        items.forEach(item => els.messages.appendChild(buildMessageNode(item)));
    }

    function buildMessageNode(item) {
        const row = document.createElement('div');
        const outgoing = item.sender_id === getCurrentUserId();
        row.className = `chat-row ${outgoing ? 'outgoing' : 'incoming'}`;

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${item.msg_type === 'EMOJI' ? 'chat-emoji' : ''}`;

        if (item.msg_type === 'IMAGE' && item.image_url) {
            if (item.content) {
                const caption = document.createElement('div');
                caption.className = 'mb-2';
                caption.textContent = item.content;
                bubble.appendChild(caption);
            }
            const img = document.createElement('img');
            img.src = item.image_url;
            img.alt = 'Chat image';
            img.className = 'chat-image';
            bubble.appendChild(img);
        } else if (item.msg_type === 'PRODUCT_LINK' && item.product) {
            const card = document.createElement('a');
            card.className = 'chat-product-card';
            card.href = `/p/${item.product.id}`;
            card.target = '_blank';
            card.rel = 'noopener';
            card.innerHTML = `
                <div class="small text-secondary">Product link</div>
                <div class="fw-semibold">${escapeHtml(item.product.title || 'View product')}</div>
            `;
            bubble.appendChild(card);
        } else {
            bubble.textContent = item.content || '';
        }

        const meta = document.createElement('div');
        meta.className = 'chat-meta';
        meta.textContent = formatDate(item.created_at);

        const wrap = document.createElement('div');
        wrap.className = 'chat-msg-wrap';
        wrap.appendChild(bubble);
        wrap.appendChild(meta);

        if (outgoing && item.read_by_peer !== null) {
            const read = document.createElement('div');
            read.className = 'chat-read';
            read.textContent = item.read_by_peer ? 'Read' : 'Unread';
            wrap.appendChild(read);
        }

        row.appendChild(wrap);
        return row;
    }

    function bindComposer() {
        if (els.sendBtn) {
            els.sendBtn.addEventListener('click', sendTextMessage);
        }
        if (els.input) {
            els.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendTextMessage();
                }
            });
        }
        if (els.imageInput) {
            els.imageInput.addEventListener('change', sendImageMessage);
        }
        if (els.productBtn) {
            els.productBtn.addEventListener('click', sendLastProduct);
        }
        if (els.emojiBtn && els.emojiPanel) {
            els.emojiBtn.addEventListener('click', () => {
                els.emojiPanel.classList.toggle('is-open');
            });
        }
    }

    async function sendTextMessage() {
        if (!state.activeId || !els.input) return;
        const text = (els.input.value || '').trim();
        if (!text) return;
        try {
            await api.post(`/api/chat/conversations/${state.activeId}/messages`, {
                msg_type: 'TEXT',
                content: text
            }, { showLoading: false });
            els.input.value = '';
            await loadMessages(state.activeId, { reset: true });
            loadConversations();
        } catch (e) {
            showToast(e.message || 'Failed to send', 'error');
        }
    }

    async function sendEmojiMessage(emoji) {
        if (!state.activeId) return;
        try {
            await api.post(`/api/chat/conversations/${state.activeId}/messages`, {
                msg_type: 'EMOJI',
                content: emoji
            }, { showLoading: false });
            await loadMessages(state.activeId, { reset: true });
            loadConversations();
        } catch (e) {
            showToast(e.message || 'Failed to send emoji', 'error');
        }
    }

    async function sendImageMessage() {
        if (!state.activeId || !els.imageInput) return;
        const file = els.imageInput.files?.[0];
        if (!file) return;
        try {
            const fd = new FormData();
            fd.append('image', file);
            const caption = (els.input?.value || '').trim();
            if (caption) fd.append('content', caption);
            await api.post(`/api/chat/conversations/${state.activeId}/messages`, fd, { showLoading: true });
            if (els.input) els.input.value = '';
            els.imageInput.value = '';
            await loadMessages(state.activeId, { reset: true });
            loadConversations();
        } catch (e) {
            showToast(e.message || 'Failed to send image', 'error');
        }
    }

    async function sendLastProduct() {
        if (!state.activeId) return;
        const last = readLastProduct();
        if (!last || !last.id) {
            showToast('No recent product found', 'info');
            return;
        }
        try {
            await api.post(`/api/chat/conversations/${state.activeId}/messages`, {
                msg_type: 'PRODUCT_LINK',
                product_id: last.id,
                content: last.title || 'Product link'
            }, { showLoading: false });
            await loadMessages(state.activeId, { reset: true });
            loadConversations();
        } catch (e) {
            showToast(e.message || 'Failed to send product link', 'error');
        }
    }

    async function markRead(conversationId) {
        try {
            await api.post(`/api/chat/conversations/${conversationId}/read`, {}, { showLoading: false });
        } catch (_) {
            // silent
        }
    }

    function renderEmojiPanel() {
        if (!els.emojiPanel) return;
        const emojis = ['😀', '😅', '😍', '😎', '😭', '😡', '👍', '🙏', '🎉', '✅', '❗', '💡', '📦', '🚚'];
        els.emojiPanel.innerHTML = emojis.map(e => `<button type="button" class="chat-emoji-btn">${e}</button>`).join('');
        els.emojiPanel.querySelectorAll('.chat-emoji-btn').forEach(btn => {
            btn.addEventListener('click', () => sendEmojiMessage(btn.textContent));
        });
    }

    function readLastProduct() {
        try {
            const raw = localStorage.getItem('shopwave_last_product');
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function updateProductButton() {
        if (!els.productBtn) return;
        const last = readLastProduct();
        const ok = last && last.id;
        els.productBtn.disabled = !ok;
        if (!ok) {
            els.productBtn.title = 'No recent product found';
        } else {
            els.productBtn.title = '';
        }
    }

    function scrollToBottom() {
        if (!els.messages) return;
        els.messages.scrollTop = els.messages.scrollHeight;
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function getCurrentUserId() {
        const raw = document.body?.dataset?.userId;
        const num = raw ? parseInt(raw, 10) : NaN;
        return Number.isFinite(num) ? num : null;
    }
}
