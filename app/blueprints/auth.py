from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    flash,
)
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user,
)
from app.extensions import db
from app.models import (
    User,
    UserRole,
    UserInterest,
    Category,
    Cart,
    MerchantProfile,
)
from app.services.audit_service import log_audit
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)


@bp.route('/api/auth/login', methods=['POST'])
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # If already logged in, redirect to home
        if current_user.is_authenticated:
            if current_user.role.value == 'MERCHANT':
                return redirect(url_for('merchant.dashboard'))
            if current_user.role.value == 'ADMIN':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('public.index'))
        if hasattr(bp, 'template_folder'):
            return render_template('auth/login.html')
        return jsonify({'message': 'Please use POST method to login'})

    # POST login
    data = request.get_json() if request.is_json else request.form
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        if request.is_json:
            return jsonify(
                {'error': 'Email and password cannot be empty'}), 400
        flash('Email and password cannot be empty', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password) and user.is_active:
        login_user(user, remember=True)
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        log_audit(
            actor_id=user.id,
            actor_role=user.role.value,
            action='LOGIN_SUCCESS',
            target_type='USER',
            target_id=user.id,
            payload={'event': 'login_success'}
        )

        if request.is_json:
            return jsonify(
                {'ok': True, 'role': user.role.value, 'user_id': user.id})
        # Redirect by role (merchant/admin should not land on public home)
        target = 'public.index'
        if user.role.value == 'MERCHANT':
            target = 'merchant.dashboard'
        elif user.role.value == 'ADMIN':
            target = 'admin.dashboard'
        return redirect(url_for(target))
    else:
        log_audit(
            actor_id=None,
            actor_role='ANONYMOUS',
            action='LOGIN_FAILED',
            target_type='USER',
            target_id=None,
            payload={
                'reason': 'invalid_credentials' if user else 'user_not_found'})

        if request.is_json:
            return jsonify({'error': 'Invalid email or password'}), 401
        flash('Invalid email or password', 'error')
        return redirect(url_for('auth.login'))


@bp.route('/api/auth/register', methods=['POST'])
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        if current_user.is_authenticated:
            return redirect(url_for('public.index'))
        # Get all active categories for selection
        categories = Category.query.filter_by(is_active=True).all()
        if hasattr(bp, 'template_folder'):
            return render_template(
                'auth/register.html',
                categories=categories,
            )
        return jsonify({
            'categories': [
                {
                    'id': c.id,
                    'name': c.name,
                    'slug': c.slug,
                }
                for c in categories
            ]
        })

    # POST register
    data = request.get_json() if request.is_json else request.form
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'CUSTOMER').upper()
    interest_category_ids = data.get('interest_category_ids', [])

    if isinstance(interest_category_ids, str):
        # Handle string format from form submission
        try:
            interest_category_ids = [
                int(x) for x in interest_category_ids.split(',') if x]
        except BaseException:
            interest_category_ids = []

    if not email or not password:
        if request.is_json:
            return jsonify(
                {'error': 'Email and password cannot be empty'}), 400
        flash('Email and password cannot be empty', 'error')
        return redirect(url_for('auth.register'))

    # Check if email already exists
    if User.query.filter_by(email=email).first():
        if request.is_json:
            return jsonify({'error': 'Email already registered'}), 400
        flash('Email already registered', 'error')
        return redirect(url_for('auth.register'))

    # Validate role
    try:
        user_role = UserRole[role]
    except KeyError:
        user_role = UserRole.CUSTOMER

    # Create user
    user = User(email=email, role=user_role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # Get user.id

    # Auto username for new users (unique & human-friendly)
    if not getattr(user, 'username', None):
        user.username = f"user{user.id}"

    # Create cart
    cart = Cart(user_id=user.id)
    db.session.add(cart)

    # Add interest categories
    if interest_category_ids:
        valid_categories = Category.query.filter(
            Category.id.in_(interest_category_ids),
            Category.is_active
        ).all()
        for category in valid_categories:
            interest = UserInterest(user_id=user.id, category_id=category.id)
            db.session.add(interest)

    db.session.commit()

    log_audit(
        actor_id=user.id,
        actor_role=user.role.value,
        action='USER_REGISTER',
        target_type='USER',
        target_id=user.id,
        payload={'role': role, 'interest_count': len(interest_category_ids)}
    )

    # Auto login
    login_user(user, remember=True)

    if request.is_json:
        return jsonify(
            {'ok': True, 'role': user.role.value, 'user_id': user.id}), 201
    flash('Registration successful!', 'success')
    return redirect(url_for('public.index'))


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'GET':
        mp = None
        if current_user.role.value == 'MERCHANT':
            mp = MerchantProfile.query.filter_by(
                user_id=current_user.id).first()
        return render_template(
            'account/settings.html',
            profile={
                'email': current_user.email,
                # For merchants we show shop_name as the effective
                # username/display handle.
                'username': getattr(current_user, 'username', None) or '',
                'role': current_user.role.value
            },
            merchant_profile=None if not mp else {
                'shop_name': mp.shop_name,
                'description': mp.description or '',
                'contact_phone': mp.contact_phone or '',
            }
        )

    # POST: supports two actions via hidden input
    form = request.form if not request.is_json else (
        request.get_json(silent=True) or {})
    action = (form.get('action') or '').strip()

    # Update username for customers.
    if action == 'profile':
        # Merchants use shop name as username.
        if current_user.role.value == 'MERCHANT':
            msg = (
                'For merchants, username matches shop name. '
                'Update your shop name instead.'
            )
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'info')
            return redirect(url_for('auth.settings'))

        # Other roles can update username.
        if current_user.role.value not in ('CUSTOMER', 'ADMIN'):
            if request.is_json:
                return jsonify({'error': 'Forbidden'}), 403
            flash('Forbidden', 'error')
            return redirect(url_for('auth.settings'))

        username = (form.get('username') or '').strip()
        # 3-20 chars, letters, numbers, underscore.
        if not re.fullmatch(r'[A-Za-z0-9_]{3,20}', username or ''):
            msg = (
                'Username must be 3-20 characters '
                '(letters, numbers, underscore).'
            )
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))

        exists = (
            User.query.filter(
                User.username == username,
                User.id != current_user.id,
            ).first()
            is not None
        )
        if exists:
            msg = 'Username already taken.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))

        old = getattr(current_user, 'username', None) or ''
        current_user.username = username
        db.session.commit()

        log_audit(
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            action='UPDATE_USERNAME',
            target_type='USER',
            target_id=current_user.id,
            payload={
                'old_len': len(old),
                'new_len': len(username),
            },
        )

        if request.is_json:
            return jsonify({'ok': True})
        flash('Username updated.', 'success')
        return redirect(url_for('auth.settings'))

    # Update merchant storefront profile.
    if action == 'merchant_profile':
        if current_user.role.value != 'MERCHANT':
            if request.is_json:
                return jsonify({'error': 'Forbidden'}), 403
            flash('Forbidden', 'error')
            return redirect(url_for('auth.settings'))

        shop_name = (form.get('shop_name') or '').strip()
        description = (form.get('description') or '').strip() or None
        contact_phone = (form.get('contact_phone') or '').strip() or None

        if len(shop_name) < 2 or len(shop_name) > 100:
            msg = 'Shop name must be 2-100 characters.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))

        exists = (
            MerchantProfile.query.filter(
                MerchantProfile.shop_name == shop_name,
                MerchantProfile.user_id != current_user.id,
            ).first()
            is not None
        )
        if exists:
            msg = 'Shop name already taken.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))

        # Enforce merchant username == shop_name across all users.
        username_conflict = (
            User.query.filter(
                User.username == shop_name,
                User.id != current_user.id,
            ).first()
            is not None
        )
        if username_conflict:
            msg = (
                'Shop name conflicts with an existing username. '
                'Please choose another shop name.'
            )
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))

        mp = MerchantProfile.query.filter_by(user_id=current_user.id).first()
        if not mp:
            mp = MerchantProfile(user_id=current_user.id, shop_name=shop_name)
            db.session.add(mp)
        mp.shop_name = shop_name
        mp.description = description
        mp.contact_phone = contact_phone
        # Sync username to shop_name
        current_user.username = shop_name
        db.session.commit()

        log_audit(
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            action='UPDATE_MERCHANT_PROFILE',
            target_type='MERCHANT_PROFILE',
            target_id=current_user.id,
            payload={
                'shop_name_len': len(shop_name),
                'has_phone': bool(contact_phone),
            },
        )

        if request.is_json:
            return jsonify({'ok': True})
        flash('Store profile updated.', 'success')
        return redirect(url_for('auth.settings'))

    # Change password.
    if action == 'password':
        old_password = form.get('old_password') or ''
        new_password = form.get('new_password') or ''
        confirm = form.get('confirm_password') or ''

        if not old_password or not new_password:
            msg = 'Old and new password cannot be empty.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))
        if new_password != confirm:
            msg = 'New password and confirmation do not match.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))
        if len(new_password) < 8:
            msg = 'New password must be at least 8 characters.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))
        if not current_user.check_password(old_password):
            msg = 'Old password is incorrect.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('auth.settings'))

        current_user.set_password(new_password)
        db.session.commit()

        log_audit(
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            action='UPDATE_PASSWORD',
            target_type='USER',
            target_id=current_user.id
        )

        if request.is_json:
            return jsonify({'ok': True})
        flash('Password updated.', 'success')
        return redirect(url_for('auth.settings'))

    if request.is_json:
        return jsonify({'error': 'Invalid action'}), 400
    flash('Invalid action', 'error')
    return redirect(url_for('auth.settings'))


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    user_id = current_user.id
    role = current_user.role.value

    log_audit(
        actor_id=user_id,
        actor_role=role,
        action='LOGOUT',
        target_type='USER',
        target_id=user_id
    )

    logout_user()

    if request.is_json:
        return jsonify({'ok': True})
    flash('Logged out', 'info')
    return redirect(url_for('public.index'))


@bp.route('/api/auth/interests', methods=['GET'])
@login_required
def get_interests():
    interests = UserInterest.query.filter_by(user_id=current_user.id).all()
    categories = [Category.query.get(ui.category_id) for ui in interests]
    return jsonify({
        'interests': [
            {'id': c.id, 'name': c.name, 'slug': c.slug}
            for c in categories
            if c
        ]
    })


@bp.route('/api/auth/interests', methods=['PUT', 'PATCH'])
@login_required
def update_interests():
    data = request.get_json()
    category_ids = data.get('interest_category_ids', [])

    if not isinstance(category_ids, list):
        return jsonify(
            {'error': 'interest_category_ids must be an array'}), 400

    # Validate categories exist and are active
    valid_categories = Category.query.filter(
        Category.id.in_(category_ids),
        Category.is_active
    ).all()
    valid_ids = [c.id for c in valid_categories]

    # Delete old interests
    UserInterest.query.filter_by(user_id=current_user.id).delete()

    # Add new interests
    for category_id in valid_ids:
        interest = UserInterest(
            user_id=current_user.id,
            category_id=category_id)
        db.session.add(interest)

    db.session.commit()

    log_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action='UPDATE_INTERESTS',
        target_type='USER',
        target_id=current_user.id,
        payload={'interest_count': len(valid_ids)}
    )

    return jsonify({
        'ok': True,
        'interests': [
            {'id': c.id, 'name': c.name, 'slug': c.slug}
            for c in valid_categories
        ]
    })
