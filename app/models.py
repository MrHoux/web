from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import CheckConstraint, UniqueConstraint
import enum
import json


class UserRole(enum.Enum):
    CUSTOMER = 'CUSTOMER'
    MERCHANT = 'MERCHANT'
    ADMIN = 'ADMIN'


class ProductStatus(enum.Enum):
    DRAFT = 'DRAFT'
    ACTIVE = 'ACTIVE'
    SUSPENDED = 'SUSPENDED'


class OrderStatus(enum.Enum):
    CREATED = 'CREATED'
    PAID = 'PAID'
    PARTIALLY_SHIPPED = 'PARTIALLY_SHIPPED'
    SHIPPED = 'SHIPPED'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'


class MerchantOrderStatus(enum.Enum):
    CREATED = 'CREATED'
    PAID = 'PAID'
    CANCELLED_BY_USER = 'CANCELLED_BY_USER'
    CANCELLED_BY_MERCHANT = 'CANCELLED_BY_MERCHANT'
    CANCELLED_BY_ADMIN = 'CANCELLED_BY_ADMIN'
    SHIPPED = 'SHIPPED'
    DELIVERED = 'DELIVERED'
    COMPLETED = 'COMPLETED'
    # Customer after-sales (return/refund) requested/processing
    AFTER_SALE = 'AFTER_SALE'
    # After-sales finished (approved+closed or rejected/closed)
    AFTER_SALE_ENDED = 'AFTER_SALE_ENDED'


class PaymentStatus(enum.Enum):
    INIT = 'INIT'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
    REFUNDED = 'REFUNDED'


class PaymentMethod(enum.Enum):
    MOCK = 'MOCK'
    ALIPAY = 'ALIPAY'
    WECHAT = 'WECHAT'
    CARD = 'CARD'


class ShippingStatus(enum.Enum):
    NOT_SHIPPED = 'NOT_SHIPPED'
    IN_TRANSIT = 'IN_TRANSIT'
    DELIVERED = 'DELIVERED'


class ItemStatus(enum.Enum):
    NORMAL = 'NORMAL'
    REFUNDING = 'REFUNDING'
    RETURNING = 'RETURNING'
    EXCHANGING = 'EXCHANGING'
    REFUNDED = 'REFUNDED'
    RETURNED = 'RETURNED'
    EXCHANGED = 'EXCHANGED'


class AfterSaleType(enum.Enum):
    RETURN = 'RETURN'
    EXCHANGE = 'EXCHANGE'
    REFUND_ONLY = 'REFUND_ONLY'


class AfterSaleStatus(enum.Enum):
    REQUESTED = 'REQUESTED'
    MERCHANT_APPROVED = 'MERCHANT_APPROVED'
    MERCHANT_REJECTED = 'MERCHANT_REJECTED'
    ADMIN_APPROVED = 'ADMIN_APPROVED'
    ADMIN_REJECTED = 'ADMIN_REJECTED'
    IN_PROGRESS = 'IN_PROGRESS'
    CLOSED = 'CLOSED'


class ModerationRequestType(enum.Enum):
    DELETE_REVIEW = 'DELETE_REVIEW'


class ModerationTargetType(enum.Enum):
    REVIEW = 'REVIEW'


class ModerationStatus(enum.Enum):
    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


class ChatConversationType(enum.Enum):
    CUSTOMER_ADMIN = 'CUSTOMER_ADMIN'
    CUSTOMER_MERCHANT = 'CUSTOMER_MERCHANT'


class ChatMessageType(enum.Enum):
    TEXT = 'TEXT'
    IMAGE = 'IMAGE'
    PRODUCT_LINK = 'PRODUCT_LINK'
    EMOJI = 'EMOJI'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    # Public handle for users.
    # Merchants use shop name as username.
    username = db.Column(
        db.String(100),
        unique=True,
        nullable=True,
        index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum(UserRole),
        nullable=False,
        default=UserRole.CUSTOMER)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    merchant_profile = db.relationship(
        'MerchantProfile',
        backref='user',
        uselist=False,
        cascade='all, delete-orphan')
    interests = db.relationship(
        'UserInterest',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan')
    cart = db.relationship(
        'Cart',
        backref='user',
        uselist=False,
        cascade='all, delete-orphan')
    orders = db.relationship('OrderGroup', backref='user', lazy='dynamic')
    reviews = db.relationship(
        'Review',
        primaryjoin='User.id==Review.user_id',
        backref='user',
        lazy='dynamic')
    wishlist_items = db.relationship(
        'WishlistItem',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan')
    addresses = db.relationship(
        'Address',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class MerchantProfile(db.Model):
    __tablename__ = 'merchant_profiles'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        primary_key=True)
    shop_name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    def __repr__(self):
        return f'<MerchantProfile {self.shop_name}>'


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    products = db.relationship(
        'ProductCategory',
        back_populates='category',
        lazy='dynamic',
        cascade='all, delete-orphan')
    user_interests = db.relationship(
        'UserInterest',
        backref='category',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    # Relative path under /static/, e.g. "uploads/products/12_abcdef.jpg"
    image_path = db.Column(db.String(255), nullable=True)
    status = db.Column(
        db.Enum(ProductStatus),
        default=ProductStatus.ACTIVE,
        nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)

    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=True)

    # Relationships
    merchant = db.relationship(
        'User',
        foreign_keys=[merchant_id],
        backref='products')
    categories = db.relationship(
        'ProductCategory',
        back_populates='product',
        lazy='dynamic',
        cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='product', lazy='dynamic')
    cart_items = db.relationship(
        'CartItem',
        backref='product',
        lazy='dynamic',
        cascade='all, delete-orphan')
    order_items = db.relationship(
        'OrderItem',
        backref='product',
        lazy='dynamic')
    wishlist_items = db.relationship(
        'WishlistItem',
        backref='product',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Product {self.title}>'


class ProductCategory(db.Model):
    __tablename__ = 'product_categories'

    product_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'products.id',
            ondelete='CASCADE'),
        primary_key=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'categories.id',
            ondelete='CASCADE'),
        primary_key=True)

    # Relationships
    product = db.relationship('Product', back_populates='categories')
    category = db.relationship('Category', back_populates='products')

    __table_args__ = (
        db.Index('idx_product_category_id', 'category_id'),
    )

    def __repr__(self):
        return (
            f"<ProductCategory product={self.product_id} "
            f"category={self.category_id}>"
        )


class UserInterest(db.Model):
    __tablename__ = 'user_interests'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        primary_key=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'categories.id',
            ondelete='CASCADE'),
        primary_key=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    __table_args__ = (
        db.Index('idx_user_interest_category_id', 'category_id'),
    )

    def __repr__(self):
        return (
            f"<UserInterest user={self.user_id} "
            f"category={self.category_id}>"
        )


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'products.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    rating = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)
    follow_up_content = db.Column(db.Text, nullable=True)
    follow_up_created_at = db.Column(db.DateTime, nullable=True)

    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    is_hidden = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=True)
    deleted_reason = db.Column(db.String(500), nullable=True)

    __table_args__ = (
        CheckConstraint(
            'rating >= 1 AND rating <= 5',
            name='check_rating_range'),
        UniqueConstraint(
            'user_id',
            'product_id',
            name='uq_user_product_review'),
    )

    def __repr__(self):
        return f'<Review {self.id} for product {self.product_id}>'


class ModerationRequest(db.Model):
    __tablename__ = 'moderation_requests'

    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.Enum(ModerationRequestType), nullable=False)
    target_type = db.Column(db.Enum(ModerationTargetType), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)  # review_id
    requester_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum(ModerationStatus),
        default=ModerationStatus.PENDING,
        nullable=False)
    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    requester = db.relationship(
        'User',
        foreign_keys=[requester_id],
        backref='moderation_requests')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    def __repr__(self):
        return f'<ModerationRequest {self.id} status={self.status}>'


class Cart(db.Model):
    __tablename__ = 'carts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        unique=True,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)

    items = db.relationship(
        'CartItem',
        backref='cart',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Cart {self.id} for user {self.user_id}>'


class CartItem(db.Model):
    __tablename__ = 'cart_items'

    cart_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'carts.id',
            ondelete='CASCADE'),
        primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'products.id',
            ondelete='CASCADE'),
        primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_quantity_positive'),
    )

    def __repr__(self):
        return (
            f"<CartItem cart={self.cart_id} product={self.product_id} "
            f"qty={self.quantity}>"
        )


class OrderGroup(db.Model):
    __tablename__ = 'order_groups'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(
        db.Enum(OrderStatus),
        default=OrderStatus.CREATED,
        nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    merchant_orders = db.relationship(
        'MerchantOrder',
        backref='order_group',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def __repr__(self):
        return f'<OrderGroup {self.id}>'


class MerchantOrder(db.Model):
    __tablename__ = 'merchant_orders'

    id = db.Column(db.Integer, primary_key=True)
    order_group_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'order_groups.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    merchant_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    status = db.Column(
        db.Enum(MerchantOrderStatus),
        default=MerchantOrderStatus.CREATED,
        nullable=False)
    cancel_deadline = db.Column(db.DateTime,
                                nullable=False)  # created_at + 5 minutes
    subtotal_amount = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)

    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=True)
    deleted_reason = db.Column(db.String(500), nullable=True)

    # Relationships
    merchant = db.relationship('User', foreign_keys=[merchant_id])
    items = db.relationship(
        'OrderItem',
        backref='merchant_order',
        lazy='dynamic',
        cascade='all, delete-orphan')
    payment = db.relationship(
        'PaymentTransaction',
        backref='merchant_order',
        uselist=False,
        cascade='all, delete-orphan')
    shipment = db.relationship(
        'Shipment',
        backref='merchant_order',
        uselist=False,
        cascade='all, delete-orphan')
    shipping_snapshot = db.relationship(
        'OrderShippingSnapshot',
        backref='merchant_order',
        uselist=False,
        cascade='all, delete-orphan')
    after_sale_requests = db.relationship(
        'AfterSaleRequest',
        backref='merchant_order',
        lazy='dynamic')

    @property
    def user_id(self):
        return self.order_group.user_id

    def __repr__(self):
        return f'<MerchantOrder {self.id} status={self.status}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    merchant_order_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'merchant_orders.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'products.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    # Order snapshot price.
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    item_status = db.Column(
        db.Enum(ItemStatus),
        default=ItemStatus.NORMAL,
        nullable=False)

    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_order_quantity_positive'),
    )

    def __repr__(self):
        return (
            f"<OrderItem {self.id} order={self.merchant_order_id} "
            f"product={self.product_id}>"
        )


class Address(db.Model):
    __tablename__ = 'addresses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    recipient_name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    province = db.Column(db.String(50), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    district = db.Column(db.String(50), nullable=False)
    detail_address = db.Column(db.Text, nullable=False)
    postal_code = db.Column(db.String(10), nullable=True)
    lat = db.Column(db.Numeric(10, 7), nullable=True)  # Latitude
    lng = db.Column(db.Numeric(10, 7), nullable=True)  # Longitude
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    def __repr__(self):
        return f'<Address {self.id} for user {self.user_id}>'


class OrderShippingSnapshot(db.Model):
    __tablename__ = 'order_shipping_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    merchant_order_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'merchant_orders.id',
            ondelete='CASCADE'),
        unique=True,
        nullable=False)
    recipient_name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    full_address_text = db.Column(db.Text, nullable=False)
    lat = db.Column(db.Numeric(10, 7), nullable=True)
    lng = db.Column(db.Numeric(10, 7), nullable=True)
    baidu_place_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    def __repr__(self):
        return f'<OrderShippingSnapshot for order {self.merchant_order_id}>'


class PaymentTransaction(db.Model):
    __tablename__ = 'payment_transactions'

    id = db.Column(db.Integer, primary_key=True)
    merchant_order_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'merchant_orders.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(
        db.Enum(PaymentStatus),
        default=PaymentStatus.INIT,
        nullable=False)
    payment_method = db.Column(
        db.Enum(PaymentMethod),
        default=PaymentMethod.MOCK,
        nullable=False)
    provider_trade_no = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)

    def __repr__(self):
        return f'<PaymentTransaction {self.id} status={self.status}>'


class OrderCancelRequest(db.Model):
    __tablename__ = 'order_cancel_requests'

    id = db.Column(db.Integer, primary_key=True)
    merchant_order_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'merchant_orders.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    # convenience for merchant queries
    merchant_id = db.Column(db.Integer, nullable=False, index=True)

    status = db.Column(
        db.String(20),
        nullable=False,
        default='PENDING')  # PENDING|APPROVED|REJECTED
    reason = db.Column(db.Text, nullable=True)
    merchant_note = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    decided_at = db.Column(db.DateTime, nullable=True)

    order = db.relationship(
        'MerchantOrder',
        backref=db.backref(
            'cancel_requests',
            lazy='dynamic',
            cascade='all, delete-orphan',
        ),
    )
    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED')",
            name='ck_order_cancel_request_status'),
    )

    def __repr__(self):
        return (
            f"<OrderCancelRequest {self.id} "
            f"order={self.merchant_order_id} status={self.status}>"
        )


class Shipment(db.Model):
    __tablename__ = 'shipments'

    id = db.Column(db.Integer, primary_key=True)
    merchant_order_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'merchant_orders.id',
            ondelete='CASCADE'),
        unique=True,
        nullable=False)
    carrier_name = db.Column(db.String(50), nullable=True)
    tracking_no = db.Column(db.String(100), nullable=True)
    shipping_status = db.Column(
        db.Enum(ShippingStatus),
        default=ShippingStatus.NOT_SHIPPED,
        nullable=False)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)

    events = db.relationship(
        'ShipmentEvent',
        backref='shipment',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Shipment {self.id} for order {self.merchant_order_id}>'


class ShipmentEvent(db.Model):
    __tablename__ = 'shipment_events'

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'shipments.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    event_time = db.Column(db.DateTime, nullable=False)
    location_text = db.Column(db.String(200), nullable=True)
    status_text = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<ShipmentEvent {self.id}>'


class AfterSaleRequest(db.Model):
    __tablename__ = 'after_sale_requests'

    id = db.Column(db.Integer, primary_key=True)
    merchant_order_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'merchant_orders.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    order_item_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'order_items.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False)
    type = db.Column(db.Enum(AfterSaleType), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum(AfterSaleStatus),
        default=AfterSaleStatus.REQUESTED,
        nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)
    resolution_note = db.Column(db.Text, nullable=True)

    # Return shipment info for returns.
    # Provided by customer after approval.
    return_carrier_name = db.Column(db.String(50), nullable=True)
    return_tracking_no = db.Column(db.String(100), nullable=True)
    return_shipping_status = db.Column(db.Enum(ShippingStatus), nullable=True)
    return_shipped_at = db.Column(db.DateTime, nullable=True)
    return_received_at = db.Column(db.DateTime, nullable=True)

    order_item = db.relationship('OrderItem', backref='after_sale_requests')
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return (
            f"<AfterSaleRequest {self.id} "
            f"type={self.type} status={self.status}>"
        )


class WishlistItem(db.Model):
    __tablename__ = 'wishlist_items'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'products.id',
            ondelete='CASCADE'),
        primary_key=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)

    def __repr__(self):
        return f'<WishlistItem user={self.user_id} product={self.product_id}>'


class ChatConversation(db.Model):
    __tablename__ = 'chat_conversations'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.Enum(ChatConversationType), nullable=False)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    merchant_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='SET NULL'),
        nullable=True,
        index=True)
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='SET NULL'),
        nullable=True,
        index=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False)
    last_message_at = db.Column(db.DateTime, nullable=True)

    customer_last_read_at = db.Column(db.DateTime, nullable=True)
    merchant_last_read_at = db.Column(db.DateTime, nullable=True)
    admin_last_read_at = db.Column(db.DateTime, nullable=True)

    customer = db.relationship('User', foreign_keys=[customer_id])
    merchant = db.relationship('User', foreign_keys=[merchant_id])
    admin = db.relationship('User', foreign_keys=[admin_id])
    messages = db.relationship(
        'ChatMessage',
        backref='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ChatConversation {self.id} type={self.type}>'


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'chat_conversations.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    sender_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='SET NULL'),
        nullable=True,
        index=True)
    sender_role = db.Column(db.String(20), nullable=False)

    msg_type = db.Column(
        db.Enum(ChatMessageType),
        nullable=False,
        default=ChatMessageType.TEXT)
    content = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'products.id',
            ondelete='SET NULL'),
        nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True)

    sender = db.relationship('User', foreign_keys=[sender_id])
    product = db.relationship('Product', foreign_keys=[product_id])

    def __repr__(self):
        return f'<ChatMessage {self.id} type={self.msg_type}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'users.id',
            ondelete='SET NULL'),
        nullable=True)
    actor_role = db.Column(db.String(20), nullable=False)
    # e.g., ORDER_CANCEL_USER, REVIEW_DELETE_REQUEST
    action = db.Column(db.String(100), nullable=False)
    # MERCHANT_ORDER, REVIEW, PRODUCT, etc.
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    # JSON format key field snapshot
    payload_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True)

    actor = db.relationship('User', foreign_keys=[actor_id])

    def set_payload(self, data):
        self.payload_json = json.dumps(data, ensure_ascii=False)

    def get_payload(self):
        if self.payload_json:
            return json.loads(self.payload_json)
        return {}

    def __repr__(self):
        return f'<AuditLog {self.id} action={self.action}>'
