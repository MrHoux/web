from datetime import datetime
import os
import uuid

from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    current_app,
    abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

from app.extensions import db
from app.middleware import role_required
from app.models import (
    ChatConversation,
    ChatMessage,
    ChatConversationType,
    ChatMessageType,
    User,
    UserRole,
    Product,
)

bp = Blueprint('chat', __name__)


def _chat_db_guard():
    try:
        db.session.execute(text("SELECT 1 FROM chat_conversations LIMIT 1"))
    except OperationalError as exc:
        raise exc


def _chat_db_error_response():
    return jsonify({
        'error': 'Chat tables are not initialized. Run: flask db upgrade'
    }), 500


def _get_admin_user():
    return User.query.filter_by(
        role=UserRole.ADMIN).order_by(
        User.id.asc()).first()


def _get_or_create_admin_conversation(customer_id: int) -> ChatConversation:
    conv = ChatConversation.query.filter_by(
        type=ChatConversationType.CUSTOMER_ADMIN,
        customer_id=customer_id
    ).first()
    if conv:
        return conv

    admin = _get_admin_user()
    if not admin:
        raise ValueError('No admin available')

    conv = ChatConversation(
        type=ChatConversationType.CUSTOMER_ADMIN,
        customer_id=customer_id,
        admin_id=admin.id
    )
    db.session.add(conv)
    db.session.commit()
    return conv


def _get_or_create_merchant_conversation(
        customer_id: int,
        merchant_id: int) -> ChatConversation:
    conv = ChatConversation.query.filter_by(
        type=ChatConversationType.CUSTOMER_MERCHANT,
        customer_id=customer_id,
        merchant_id=merchant_id
    ).first()
    if conv:
        return conv

    conv = ChatConversation(
        type=ChatConversationType.CUSTOMER_MERCHANT,
        customer_id=customer_id,
        merchant_id=merchant_id
    )
    db.session.add(conv)
    db.session.commit()
    return conv


def _conversation_accessible(conv: ChatConversation, user: User) -> bool:
    if user.role == UserRole.ADMIN:
        return conv.type == ChatConversationType.CUSTOMER_ADMIN
    if user.role == UserRole.MERCHANT:
        return (
            conv.type == ChatConversationType.CUSTOMER_MERCHANT
            and conv.merchant_id == user.id
        )
    if user.role == UserRole.CUSTOMER:
        return conv.customer_id == user.id
    return False


def _get_last_read_at(conv: ChatConversation, user: User):
    if user.role == UserRole.ADMIN:
        return conv.admin_last_read_at
    if user.role == UserRole.MERCHANT:
        return conv.merchant_last_read_at
    return conv.customer_last_read_at


def _set_last_read_at(conv: ChatConversation, user: User, ts=None):
    ts = ts or datetime.utcnow()
    if user.role == UserRole.ADMIN:
        conv.admin_last_read_at = ts
    elif user.role == UserRole.MERCHANT:
        conv.merchant_last_read_at = ts
    else:
        conv.customer_last_read_at = ts


def _peer_last_read_at(conv: ChatConversation, user: User):
    if user.role == UserRole.ADMIN:
        return conv.customer_last_read_at
    if user.role == UserRole.MERCHANT:
        return conv.customer_last_read_at
    # customer
    if conv.type == ChatConversationType.CUSTOMER_ADMIN:
        return conv.admin_last_read_at
    return conv.merchant_last_read_at


def _compute_unread_count(conv: ChatConversation, user: User) -> int:
    last_read = _get_last_read_at(conv, user)
    q = ChatMessage.query.filter(ChatMessage.conversation_id == conv.id)
    if user.role == UserRole.CUSTOMER:
        q = q.filter(ChatMessage.sender_id != user.id)
    elif user.role == UserRole.MERCHANT:
        q = q.filter(ChatMessage.sender_id != user.id)
    elif user.role == UserRole.ADMIN:
        q = q.filter(ChatMessage.sender_id != user.id)
    if last_read:
        q = q.filter(ChatMessage.created_at > last_read)
    return q.count()


def _last_message_preview(msg):
    if not msg:
        return None, None
    if msg.msg_type == ChatMessageType.IMAGE:
        return 'Image', msg.msg_type.value
    if msg.msg_type == ChatMessageType.PRODUCT_LINK:
        return 'Product link', msg.msg_type.value
    if msg.msg_type == ChatMessageType.EMOJI:
        return msg.content or 'Emoji', msg.msg_type.value
    return msg.content or '', msg.msg_type.value


def _save_chat_image(file_storage) -> str:
    filename = secure_filename(file_storage.filename or '')
    ext = (filename.rsplit('.', 1)[-1] if '.' in filename else '').lower()
    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        raise ValueError('Unsupported image type (jpg/jpeg/png/webp/gif only)')

    rel_dir = os.path.join('uploads', 'chat')
    abs_dir = os.path.join(current_app.static_folder, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    new_name = f"{uuid.uuid4().hex}.{ext}"
    abs_path = os.path.join(abs_dir, new_name)
    file_storage.save(abs_path)
    return f"{rel_dir}/{new_name}".replace('\\', '/')


@bp.route('/support/chat', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def customer_chat_page():
    merchant_id = request.args.get('merchant_id', type=int)
    return render_template('chat/support.html', merchant_id=merchant_id)


@bp.route('/admin/messages', methods=['GET'])
@login_required
@role_required('ADMIN')
def admin_chat_page():
    return render_template('chat/admin.html')


@bp.route('/merchant/messages', methods=['GET'])
@login_required
@role_required('MERCHANT')
def merchant_chat_page():
    return render_template('chat/merchant.html')


@bp.route('/api/chat/admin/start', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def start_admin_chat():
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    try:
        conv = _get_or_create_admin_conversation(current_user.id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'conversation_id': conv.id})


@bp.route('/api/chat/merchant/start', methods=['POST'])
@login_required
@role_required('CUSTOMER')
def start_merchant_chat():
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    data = request.get_json(silent=True) or {}
    merchant_id = data.get('merchant_id')
    if not merchant_id:
        return jsonify({'error': 'merchant_id required'}), 400

    merchant = User.query.filter_by(
        id=merchant_id, role=UserRole.MERCHANT).first()
    if not merchant:
        return jsonify({'error': 'Merchant not found'}), 404

    conv = _get_or_create_merchant_conversation(current_user.id, merchant_id)
    return jsonify({'ok': True, 'conversation_id': conv.id})


@bp.route('/api/chat/conversations', methods=['GET'])
@login_required
@role_required('CUSTOMER')
def list_customer_conversations():
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    convs = ChatConversation.query.filter_by(
        customer_id=current_user.id).order_by(
        ChatConversation.last_message_at.desc().nullslast(),
        ChatConversation.updated_at.desc()).all()

    items = []
    for c in convs:
        last_msg = ChatMessage.query.filter_by(
            conversation_id=c.id).order_by(
            ChatMessage.created_at.desc()).first()
        last_preview, last_type = _last_message_preview(last_msg)
        peer_label = 'Support'
        peer_id = None
        if c.type == ChatConversationType.CUSTOMER_MERCHANT:
            peer_id = c.merchant_id
            mp = None
            if c.merchant:
                mp = getattr(c.merchant, 'merchant_profile', None)
            peer_label = (
                mp.shop_name
                if mp and mp.shop_name
                else f"Merchant #{peer_id}"
            )

        items.append({
            'id': c.id,
            'type': c.type.value,
            'peer': {
                'id': peer_id,
                'label': peer_label
            },
            'last_message': last_preview,
            'last_message_type': last_type,
            'last_message_at': (
                last_msg.created_at.isoformat() if last_msg else None
            ),
            'unread_count': _compute_unread_count(c, current_user)
        })

    return jsonify({'items': items})


@bp.route('/api/chat/admin/conversations', methods=['GET'])
@login_required
@role_required('ADMIN')
def list_admin_conversations():
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    convs = ChatConversation.query.filter_by(
        type=ChatConversationType.CUSTOMER_ADMIN).order_by(
        ChatConversation.last_message_at.desc().nullslast(),
        ChatConversation.updated_at.desc()).all()

    items = []
    for c in convs:
        last_msg = ChatMessage.query.filter_by(
            conversation_id=c.id).order_by(
            ChatMessage.created_at.desc()).first()
        last_preview, last_type = _last_message_preview(last_msg)
        customer_email = c.customer.email if c.customer else None
        items.append({
            'id': c.id,
            'type': c.type.value,
            'peer': {
                'id': c.customer_id,
                'label': customer_email or f'User #{c.customer_id}'
            },
            'last_message': last_preview,
            'last_message_type': last_type,
            'last_message_at': (
                last_msg.created_at.isoformat() if last_msg else None
            ),
            'unread_count': _compute_unread_count(c, current_user)
        })

    return jsonify({'items': items})


@bp.route('/api/chat/merchant/conversations', methods=['GET'])
@login_required
@role_required('MERCHANT')
def list_merchant_conversations():
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    convs = ChatConversation.query.filter_by(
        type=ChatConversationType.CUSTOMER_MERCHANT,
        merchant_id=current_user.id).order_by(
        ChatConversation.last_message_at.desc().nullslast(),
        ChatConversation.updated_at.desc()).all()

    items = []
    for c in convs:
        last_msg = ChatMessage.query.filter_by(
            conversation_id=c.id).order_by(
            ChatMessage.created_at.desc()).first()
        last_preview, last_type = _last_message_preview(last_msg)
        customer_email = c.customer.email if c.customer else None
        items.append({
            'id': c.id,
            'type': c.type.value,
            'peer': {
                'id': c.customer_id,
                'label': customer_email or f'User #{c.customer_id}'
            },
            'last_message': last_preview,
            'last_message_type': last_type,
            'last_message_at': (
                last_msg.created_at.isoformat() if last_msg else None
            ),
            'unread_count': _compute_unread_count(c, current_user)
        })

    return jsonify({'items': items})


@bp.route('/api/chat/conversations/<int:conversation_id>/messages',
          methods=['GET'])
@login_required
def get_messages(conversation_id):
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    conv = ChatConversation.query.get_or_404(conversation_id)
    if not _conversation_accessible(conv, current_user):
        abort(403)

    after_id = request.args.get('after_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    if limit > 200:
        limit = 200

    q = ChatMessage.query.filter_by(
        conversation_id=conv.id).order_by(
        ChatMessage.created_at.asc())
    if after_id:
        q = q.filter(ChatMessage.id > after_id)

    msgs = q.limit(limit).all()

    peer_read_at = _peer_last_read_at(conv, current_user)
    items = []
    for m in msgs:
        read_by_peer = None
        if m.sender_id == current_user.id:
            read_by_peer = (
                peer_read_at is not None and m.created_at <= peer_read_at
            )
        items.append({
            'id': m.id,
            'sender_id': m.sender_id,
            'sender_role': m.sender_role,
            'msg_type': m.msg_type.value,
            'content': m.content,
            'image_url': (
                f"/static/{m.image_path}" if m.image_path else None
            ),
            'product': (
                {
                    'id': m.product_id,
                    'title': m.product.title if m.product else None
                } if m.product_id else None
            ),
            'created_at': m.created_at.isoformat(),
            'read_by_peer': read_by_peer
        })

    # If this is the initial fetch, mark as read.
    if not after_id and msgs:
        _set_last_read_at(conv, current_user)
        db.session.commit()

    return jsonify({
        'items': items,
        'conversation': {
            'id': conv.id,
            'type': conv.type.value,
            'customer_id': conv.customer_id,
            'merchant_id': conv.merchant_id,
            'admin_id': conv.admin_id
        }
    })


@bp.route('/api/chat/conversations/<int:conversation_id>/read',
          methods=['POST'])
@login_required
def mark_read(conversation_id):
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    conv = ChatConversation.query.get_or_404(conversation_id)
    if not _conversation_accessible(conv, current_user):
        abort(403)
    _set_last_read_at(conv, current_user)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/api/chat/conversations/<int:conversation_id>/messages',
          methods=['POST'])
@login_required
def send_message(conversation_id):
    try:
        _chat_db_guard()
    except OperationalError:
        return _chat_db_error_response()
    conv = ChatConversation.query.get_or_404(conversation_id)
    if not _conversation_accessible(conv, current_user):
        abort(403)

    msg = ChatMessage(
        conversation_id=conv.id,
        sender_id=current_user.id,
        sender_role=current_user.role.value
    )

    if request.files:
        f = request.files.get('image')
        if not f:
            return jsonify({'error': 'image file required'}), 400
        try:
            msg.image_path = _save_chat_image(f)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        msg.msg_type = ChatMessageType.IMAGE
        msg.content = (request.form.get('content') or '').strip() or None
    else:
        data = request.get_json(silent=True) or {}
        msg_type = (data.get('msg_type') or 'TEXT').upper()
        content = (data.get('content') or '').strip()

        if msg_type == 'PRODUCT_LINK':
            product_id = data.get('product_id')
            if not product_id:
                return jsonify({'error': 'product_id required'}), 400
            product = Product.query.get(product_id)
            if not product:
                return jsonify({'error': 'Product not found'}), 404
            msg.product_id = product_id
            msg.msg_type = ChatMessageType.PRODUCT_LINK
            msg.content = content or product.title
        elif msg_type == 'EMOJI':
            msg.msg_type = ChatMessageType.EMOJI
            msg.content = content
        else:
            msg.msg_type = ChatMessageType.TEXT
            msg.content = content

        if not msg.content and msg.msg_type != ChatMessageType.PRODUCT_LINK:
            return jsonify({'error': 'Message cannot be empty'}), 400

    now = datetime.utcnow()
    conv.last_message_at = now
    conv.updated_at = now

    db.session.add(msg)
    db.session.commit()

    return jsonify({'ok': True, 'message_id': msg.id})
