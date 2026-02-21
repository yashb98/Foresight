"""Initial schema — all 6 core tables

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-02-20 00:00:00.000000

Creates the full FORESIGHT PostgreSQL schema in a single migration:
  - tenants
  - assets
  - asset_health_scores
  - threshold_rules
  - alerts
  - maintenance_records

All tables include:
  - UUID primary keys
  - tenant_id for multi-tenancy isolation
  - Compound indexes on (tenant_id, ...) for query performance
  - JSONB columns for flexible metadata
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ENUMS — create once, shared across tables
    # ------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE subscription_tier_enum AS ENUM ('starter', 'professional', 'enterprise');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE asset_type_enum AS ENUM (
                'pump', 'turbine', 'transformer', 'compressor',
                'motor', 'valve', 'conveyor', 'generator'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE criticality_enum AS ENUM ('low', 'medium', 'high', 'critical');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE severity_enum AS ENUM ('low', 'medium', 'high', 'critical');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE rule_operator_enum AS ENUM ('gt', 'lt', 'gte', 'lte', 'eq');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE alert_status_enum AS ENUM ('active', 'acknowledged', 'resolved');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE source_system_enum AS ENUM ('sap', 'asset_suite', 'manual');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # ------------------------------------------------------------------
    # tenants
    # ------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("tenant_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config_json", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "subscription_tier",
            sa.Enum("starter", "professional", "enterprise",
                    name="subscription_tier_enum", create_type=False),
            nullable=False,
            server_default="starter",
        ),
        sa.Column("client_id", sa.String(128), nullable=False, unique=True),
        sa.Column("client_secret_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_tenants_client_id", "tenants", ["client_id"])
    op.create_index("idx_tenants_active", "tenants", ["is_active"])

    # ------------------------------------------------------------------
    # assets
    # ------------------------------------------------------------------
    op.create_table(
        "assets",
        sa.Column("asset_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "asset_type",
            sa.Enum("pump", "turbine", "transformer", "compressor",
                    "motor", "valve", "conveyor", "generator",
                    name="asset_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column(
            "criticality",
            sa.Enum("low", "medium", "high", "critical",
                    name="criticality_enum", create_type=False),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("installed_date", sa.Date, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("source_system", sa.String(50), nullable=True),
        sa.Column("source_asset_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_assets_tenant_id", "assets", ["tenant_id"])
    op.create_index("idx_assets_tenant_type", "assets", ["tenant_id", "asset_type"])
    op.create_index("idx_assets_source", "assets",
                    ["tenant_id", "source_system", "source_asset_id"])

    # ------------------------------------------------------------------
    # asset_health_scores
    # ------------------------------------------------------------------
    op.create_table(
        "asset_health_scores",
        sa.Column("score_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=False),
                  sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=False), nullable=False),
        sa.Column("score_date", sa.Date, nullable=False),
        sa.Column("health_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("failure_prob_7d", sa.Numeric(6, 4), nullable=False),
        sa.Column("failure_prob_30d", sa.Numeric(6, 4), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False,
                  server_default="foresight-failure-predictor"),
        sa.Column("top_features_json", JSONB, nullable=False, server_default="[]"),
        sa.Column("confidence_lower", sa.Numeric(6, 4), nullable=True),
        sa.Column("confidence_upper", sa.Numeric(6, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("asset_id", "score_date", name="uq_asset_score_date"),
    )
    op.create_index("idx_scores_tenant_date", "asset_health_scores", ["tenant_id", "score_date"])
    op.create_index("idx_scores_asset_date", "asset_health_scores", ["asset_id", "score_date"])
    op.create_index("idx_scores_high_risk", "asset_health_scores",
                    ["tenant_id", "failure_prob_30d"])

    # ------------------------------------------------------------------
    # threshold_rules
    # ------------------------------------------------------------------
    op.create_table(
        "threshold_rules",
        sa.Column("rule_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(50), nullable=True),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column(
            "operator",
            sa.Enum("gt", "lt", "gte", "lte", "eq",
                    name="rule_operator_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("threshold_value", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("low", "medium", "high", "critical",
                    name="severity_enum", create_type=False),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_rules_tenant_active", "threshold_rules", ["tenant_id", "active"])
    op.create_index("idx_rules_tenant_metric", "threshold_rules", ["tenant_id", "metric_name"])

    # ------------------------------------------------------------------
    # alerts
    # ------------------------------------------------------------------
    op.create_table(
        "alerts",
        sa.Column("alert_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=False),
                  sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", UUID(as_uuid=False),
                  sa.ForeignKey("threshold_rules.rule_id", ondelete="SET NULL"), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=False, server_default="threshold_breach"),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column("actual_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("threshold_value", sa.Numeric(12, 4), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("low", "medium", "high", "critical",
                    name="severity_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "acknowledged", "resolved",
                    name="alert_status_enum", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("triggered_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_alerts_tenant_status", "alerts", ["tenant_id", "status"])
    op.create_index("idx_alerts_tenant_triggered", "alerts", ["tenant_id", "triggered_at"])
    op.create_index("idx_alerts_asset_active", "alerts", ["asset_id", "status"])

    # ------------------------------------------------------------------
    # maintenance_records
    # ------------------------------------------------------------------
    op.create_table(
        "maintenance_records",
        sa.Column("record_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=False),
                  sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=False), nullable=False),
        sa.Column("maintenance_type", sa.String(100), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("outcome", sa.String(255), nullable=True),
        sa.Column(
            "source_system",
            sa.Enum("sap", "asset_suite", "manual",
                    name="source_system_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("source_record_id", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_maintenance_tenant_asset", "maintenance_records",
                    ["tenant_id", "asset_id"])
    op.create_index("idx_maintenance_asset_date", "maintenance_records",
                    ["asset_id", "performed_at"])
    op.create_index("idx_maintenance_source", "maintenance_records",
                    ["source_system", "source_record_id"])


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.drop_table("maintenance_records")
    op.drop_table("alerts")
    op.drop_table("threshold_rules")
    op.drop_table("asset_health_scores")
    op.drop_table("assets")
    op.drop_table("tenants")

    # Drop enums
    for enum_name in [
        "source_system_enum", "alert_status_enum", "rule_operator_enum",
        "severity_enum", "criticality_enum", "asset_type_enum", "subscription_tier_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
