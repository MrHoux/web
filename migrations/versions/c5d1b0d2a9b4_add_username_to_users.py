from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c5d1b0d2a9b4"
down_revision = "88065e0aa5c1"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite-safe add column
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("username", sa.String(length=32), nullable=True)
        )

    # Backfill existing users with deterministic unique usernames (user{id})
    op.execute(
        "UPDATE users SET username = 'user' || id "
        "WHERE username IS NULL OR TRIM(username) = ''"
    )

    # Create unique index after backfill
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index("ix_users_username", ["username"], unique=True)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_username")
        batch_op.drop_column("username")
