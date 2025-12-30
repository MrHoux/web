from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6a8e8a6f0e5c"
down_revision = "df0d7b6a1f2a"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("image_path", sa.String(length=255), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("image_path")
