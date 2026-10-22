
"""Create the customers table."""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_customers"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("tenure_months", sa.Integer(), nullable=False),
        sa.Column("subscription_plan", sa.String(length=50), nullable=True),
        sa.Column("monthly_spend", sa.Numeric(12, 2), nullable=False),
        sa.Column("usage_30d", sa.Numeric(12, 2), nullable=False),
        sa.Column("support_tickets_90d", sa.Integer(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tenure_months >= 0",
            name="ck_customers_tenure_nonnegative",
        ),
        sa.CheckConstraint(
            "monthly_spend >= 0",
            name="ck_customers_spend_nonnegative",
        ),
        sa.CheckConstraint(
            "usage_30d >= 0",
            name="ck_customers_usage_nonnegative",
        ),
        sa.CheckConstraint(
            "support_tickets_90d >= 0",
            name="ck_customers_tickets_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "external_id",
            name="uq_customers_tenant_external_id",
        ),
    )

    op.create_index(
        "ix_customers_tenant_id",
        "customers",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customers_tenant_id",
        table_name="customers",
    )
    op.drop_table("customers")
