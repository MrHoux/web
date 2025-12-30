from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3a1f4d2e9aa"
down_revision = "b7c9d8e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    old = sa.Enum(
        "CREATED",
        "PAID",
        "CANCELLED_BY_USER",
        "CANCELLED_BY_MERCHANT",
        "CANCELLED_BY_ADMIN",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        name="merchantorderstatus",
    )
    new = sa.Enum(
        "CREATED",
        "PAID",
        "CANCELLED_BY_USER",
        "CANCELLED_BY_MERCHANT",
        "CANCELLED_BY_ADMIN",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        "AFTER_SALE",
        "AFTER_SALE_ENDED",
        name="merchantorderstatus",
    )
    with op.batch_alter_table("merchant_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "status", existing_type=old, type_=new, existing_nullable=False
        )


def downgrade():
    new = sa.Enum(
        "CREATED",
        "PAID",
        "CANCELLED_BY_USER",
        "CANCELLED_BY_MERCHANT",
        "CANCELLED_BY_ADMIN",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        "AFTER_SALE",
        "AFTER_SALE_ENDED",
        name="merchantorderstatus",
    )
    old = sa.Enum(
        "CREATED",
        "PAID",
        "CANCELLED_BY_USER",
        "CANCELLED_BY_MERCHANT",
        "CANCELLED_BY_ADMIN",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        name="merchantorderstatus",
    )
    with op.batch_alter_table("merchant_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "status", existing_type=new, type_=old, existing_nullable=False
        )
