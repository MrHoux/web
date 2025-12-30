from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4b2c7d9f1a0"
down_revision = "1f2a3b4c5d6e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("reviews", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("follow_up_content", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("follow_up_created_at", sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("reviews", schema=None) as batch_op:
        batch_op.drop_column("follow_up_created_at")
        batch_op.drop_column("follow_up_content")
