"""Create or upgrade the production pond-analysis schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260822_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pond_analysis" not in inspector.get_table_names():
        op.create_table(
            "pond_analysis",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("analysis_status", sa.String(), nullable=False, server_default="incomplete"),
            sa.Column("village_name", sa.String(length=200), nullable=True),
            sa.Column("center_lat", sa.Float(), nullable=False),
            sa.Column("center_lng", sa.Float(), nullable=False),
            sa.Column("min_elevation", sa.Float()),
            sa.Column("max_elevation", sa.Float()),
            sa.Column("mean_elevation", sa.Float()),
            sa.Column("relief", sa.Float()),
            sa.Column("catchment_area_sqm", sa.Float()),
            sa.Column("annual_rainfall_mm", sa.Float()),
            sa.Column("runoff_coefficient", sa.Float()),
            sa.Column("estimated_volume_m3", sa.Float()),
            sa.Column("bare_surface_ratio", sa.Float()),
            sa.Column("pond_lat", sa.Float()),
            sa.Column("pond_lng", sa.Float()),
            sa.Column("depth_m", sa.Float()),
            sa.Column("capacity_m3", sa.Float()),
            sa.Column("surface_area_sqm", sa.Float()),
            sa.Column("catchment_polygon", sa.JSON()),
            sa.Column("candidate_land_polygon", sa.JSON()),
            sa.Column("contours", sa.JSON()),
            sa.Column("monthly_rainfall", sa.JSON()),
            sa.Column("source_metadata", sa.JSON()),
            sa.Column("warnings", sa.JSON()),
        )
        op.create_index("ix_pond_analysis_id", "pond_analysis", ["id"])
        op.create_index("ix_pond_analysis_created_at", "pond_analysis", ["created_at"])
        return

    columns = {column["name"] for column in inspector.get_columns("pond_analysis")}
    if "analysis_status" not in columns:
        op.add_column("pond_analysis", sa.Column("analysis_status", sa.String(), nullable=False, server_default="incomplete"))
    if "barren_ratio" in columns and "bare_surface_ratio" not in columns:
        op.alter_column("pond_analysis", "barren_ratio", new_column_name="bare_surface_ratio")
    elif "bare_surface_ratio" not in columns:
        op.add_column("pond_analysis", sa.Column("bare_surface_ratio", sa.Float()))
    if "government_land_polygon" in columns and "candidate_land_polygon" not in columns:
        op.alter_column("pond_analysis", "government_land_polygon", new_column_name="candidate_land_polygon")
    elif "candidate_land_polygon" not in columns:
        op.add_column("pond_analysis", sa.Column("candidate_land_polygon", sa.JSON()))
    if "source_metadata" not in columns:
        op.add_column("pond_analysis", sa.Column("source_metadata", sa.JSON()))
    if "warnings" not in columns:
        op.add_column("pond_analysis", sa.Column("warnings", sa.JSON()))
    indexes = {index["name"] for index in inspector.get_indexes("pond_analysis")}
    if "ix_pond_analysis_created_at" not in indexes:
        op.create_index("ix_pond_analysis_created_at", "pond_analysis", ["created_at"])


def downgrade() -> None:
    # Production data is intentionally preserved; use a reviewed manual rollback.
    pass
