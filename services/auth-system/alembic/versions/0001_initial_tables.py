"""create initial tables: payments + payment_stats"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# -------------------------------
# Revision identifiers
# -------------------------------
revision = "0001_initial_tables"
down_revision = None
branch_labels = None
depends_on = None

# -------------------------------
# Upgrade / Downgrade
# -------------------------------
def upgrade():
    # -------------------------------
    # payments table
    # -------------------------------
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),

        # Payment info
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),

        # User info
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("user_name", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),

        # Card info
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("card_brand", sa.String(32), nullable=True),
        sa.Column("card_type", sa.String(16), nullable=True),
        sa.Column("network", sa.String(64), nullable=True),
        sa.Column("network_reference_id", sa.Text(), nullable=True),

        # Financial breakdown
        sa.Column("paypal_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=True),

        # Transaction metadata
        sa.Column("order_id", sa.Text(), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("method", sa.String(32), nullable=True),
        sa.Column("billing_full_name", sa.Text(), nullable=True),
        sa.Column("billing_country", sa.String(64), nullable=True),
        sa.Column("payment_type", sa.String(16), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # -------------------------------
    # payment_stats table
    # -------------------------------
    op.create_table(
        "payment_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),  # Format: YYYY-MM
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade():
    # Drop tables in reverse order
    op.drop_table("payment_stats")
    op.drop_table("payments")
