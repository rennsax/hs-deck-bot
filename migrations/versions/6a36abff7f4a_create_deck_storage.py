"""initialize

Revision ID: 6a36abff7f4a
Revises:
Create Date: 2026-11-06 18:30:38.454303

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a36abff7f4a"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial deck storage schema."""

    op.create_table(
        "cards",
        sa.Column("dbf_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=True),
        sa.Column("card_type", sa.String(length=32), nullable=True),
        sa.Column("card_class", sa.String(length=32), nullable=True),
        sa.Column("collectible", sa.Boolean(), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("dbf_id", name=op.f("pk_cards")),
        sa.UniqueConstraint("card_id", name="uq_cards_card_id"),
    )
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.create_index("ix_cards_name", ["name"], unique=False)

    op.create_table(
        "card_catalog_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "card_count > 0",
            name=op.f("ck_card_catalog_state_card_count_positive"),
        ),
        sa.CheckConstraint(
            "id = 1",
            name=op.f("ck_card_catalog_state_singleton"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_catalog_state")),
    )

    op.create_table(
        "decks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("creator_name", sa.String(length=255), nullable=False),
        sa.Column("class_key", sa.String(length=32), nullable=False),
        sa.Column("format_id", sa.Integer(), nullable=False),
        sa.Column("hero_dbf_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["hero_dbf_id"],
            ["cards.dbf_id"],
            name=op.f("fk_decks_hero_dbf_id_cards"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decks")),
        sa.UniqueConstraint(
            "creator_name",
            "name",
            name="uq_decks_creator_name",
        ),
    )
    with op.batch_alter_table("decks", schema=None) as batch_op:
        batch_op.create_index("ix_decks_name", ["name"], unique=False)

    op.create_table(
        "deck_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deck_id", sa.Integer(), nullable=False),
        sa.Column("card_dbf_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("zone", sa.String(length=16), nullable=False),
        sa.Column("sideboard_owner_dbf_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(zone = 'main' AND sideboard_owner_dbf_id IS NULL) OR "
            "(zone = 'sideboard' AND sideboard_owner_dbf_id IS NOT NULL)",
            name=op.f("ck_deck_cards_zone_owner_consistent"),
        ),
        sa.CheckConstraint(
            "zone IN ('main', 'sideboard')",
            name=op.f("ck_deck_cards_zone_valid"),
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name=op.f("ck_deck_cards_quantity_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["card_dbf_id"],
            ["cards.dbf_id"],
            name=op.f("fk_deck_cards_card_dbf_id_cards"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deck_id"],
            ["decks.id"],
            name=op.f("fk_deck_cards_deck_id_decks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sideboard_owner_dbf_id"],
            ["cards.dbf_id"],
            name=op.f("fk_deck_cards_sideboard_owner_dbf_id_cards"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deck_cards")),
    )
    with op.batch_alter_table("deck_cards", schema=None) as batch_op:
        batch_op.create_index(
            "ix_deck_cards_card_dbf_id",
            ["card_dbf_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_deck_cards_deck_id",
            ["deck_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_deck_cards_sideboard_owner",
            ["sideboard_owner_dbf_id"],
            unique=False,
        )
        batch_op.create_index(
            "uq_deck_cards_main_card",
            ["deck_id", "card_dbf_id"],
            unique=True,
            sqlite_where=sa.text("zone = 'main'"),
            postgresql_where=sa.text("zone = 'main'"),
        )
        batch_op.create_index(
            "uq_deck_cards_sideboard_card_owner",
            ["deck_id", "card_dbf_id", "sideboard_owner_dbf_id"],
            unique=True,
            sqlite_where=sa.text("zone = 'sideboard'"),
            postgresql_where=sa.text("zone = 'sideboard'"),
        )


def downgrade() -> None:
    """Drop the initial deck storage schema."""

    with op.batch_alter_table("deck_cards", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_deck_cards_sideboard_card_owner",
            sqlite_where=sa.text("zone = 'sideboard'"),
            postgresql_where=sa.text("zone = 'sideboard'"),
        )
        batch_op.drop_index(
            "uq_deck_cards_main_card",
            sqlite_where=sa.text("zone = 'main'"),
            postgresql_where=sa.text("zone = 'main'"),
        )
        batch_op.drop_index("ix_deck_cards_sideboard_owner")
        batch_op.drop_index("ix_deck_cards_deck_id")
        batch_op.drop_index("ix_deck_cards_card_dbf_id")

    op.drop_table("deck_cards")
    with op.batch_alter_table("decks", schema=None) as batch_op:
        batch_op.drop_index("ix_decks_name")

    op.drop_table("decks")
    op.drop_table("card_catalog_state")
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.drop_index("ix_cards_name")

    op.drop_table("cards")
