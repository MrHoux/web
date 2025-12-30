from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "df0d7b6a1f2a"
down_revision = "c5d1b0d2a9b4"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite-safe: recreate table via batch ops
    with op.batch_alter_table("users", schema=None) as batch_op:
        try:
            batch_op.drop_index("ix_users_username")
        except Exception:
            pass
        batch_op.alter_column(
            "username",
            existing_type=sa.String(length=32),
            type_=sa.String(length=100),
            existing_nullable=True,
        )

    # Sync merchant usernames to shop names when no conflict exists.
    # Keep existing usernames if a conflict exists.
    op.execute(
        "UPDATE users\n"
        "SET username = (\n"
        "    SELECT mp.shop_name FROM merchant_profiles mp\n"
        "    WHERE mp.user_id = users.id\n"
        ")\n"
        "WHERE users.role = 'MERCHANT'\n"
        "  AND EXISTS (\n"
        "      SELECT 1 FROM merchant_profiles mp2\n"
        "      WHERE mp2.user_id = users.id\n"
        "  )\n"
        "  AND NOT EXISTS (\n"
        "      SELECT 1 FROM users u2\n"
        "      WHERE u2.id != users.id\n"
        "        AND u2.username = (\n"
        "            SELECT mp3.shop_name FROM merchant_profiles mp3\n"
        "            WHERE mp3.user_id = users.id\n"
        "        )\n"
        "  )\n"
    )

    # Recreate unique index
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index("ix_users_username", ["username"], unique=True)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        try:
            batch_op.drop_index("ix_users_username")
        except Exception:
            pass
        batch_op.alter_column(
            "username",
            existing_type=sa.String(length=100),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
        batch_op.create_index("ix_users_username", ["username"], unique=True)
