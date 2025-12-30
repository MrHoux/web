from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c9d8e1f2a3"
down_revision = "6a8e8a6f0e5c"
branch_labels = None
depends_on = None


def upgrade():
    # shippingstatus enum already exists from initial migration; reuse it.
    shippingstatus = sa.Enum(
        "NOT_SHIPPED", "IN_TRANSIT", "DELIVERED", name="shippingstatus"
    )

    with op.batch_alter_table("after_sale_requests", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "return_carrier_name", sa.String(length=50), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "return_tracking_no", sa.String(length=100), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("return_shipping_status", shippingstatus, nullable=True)
        )
        batch_op.add_column(
            sa.Column("return_shipped_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("return_received_at", sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("after_sale_requests", schema=None) as batch_op:
        batch_op.drop_column("return_received_at")
        batch_op.drop_column("return_shipped_at")
        batch_op.drop_column("return_shipping_status")
        batch_op.drop_column("return_tracking_no")
        batch_op.drop_column("return_carrier_name")
