"""SQLAlchemy ORM models for public Hearthstone decks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by all database models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """UTC timestamps common to persisted records."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class CardModel(Base):
    """A localized Hearthstone card identified by its DBF ID."""

    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_cards_card_id"),
        Index("ix_cards_name", "name"),
    )

    dbf_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cost: Mapped[int | None] = mapped_column(Integer)
    card_type: Mapped[str | None] = mapped_column(String(32))
    card_class: Mapped[str | None] = mapped_column(String(32))
    collectible: Mapped[bool | None] = mapped_column(Boolean)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    deck_entries: Mapped[list[DeckCardModel]] = relationship(
        back_populates="card",
        foreign_keys="DeckCardModel.card_dbf_id",
    )
    owned_sideboard_entries: Mapped[list[DeckCardModel]] = relationship(
        back_populates="sideboard_owner",
        foreign_keys="DeckCardModel.sideboard_owner_dbf_id",
    )
    hero_decks: Mapped[list[DeckModel]] = relationship(
        back_populates="hero_card",
        foreign_keys="DeckModel.hero_dbf_id",
    )


class CardCatalogStateModel(Base):
    """Freshness metadata for the complete card catalog."""

    __tablename__ = "card_catalog_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("card_count > 0", name="card_count_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    card_count: Mapped[int] = mapped_column(Integer, nullable=False)


class DeckModel(TimestampMixin, Base):
    """A named public deck attributed to a user-provided creator name."""

    __tablename__ = "decks"
    __table_args__ = (
        UniqueConstraint(
            "creator_name",
            "name",
            name="uq_decks_creator_name",
        ),
        Index("ix_decks_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    class_key: Mapped[str] = mapped_column(String(32), nullable=False)
    format_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hero_dbf_id: Mapped[int] = mapped_column(
        ForeignKey("cards.dbf_id", ondelete="RESTRICT"),
        nullable=False,
    )

    hero_card: Mapped[CardModel] = relationship(
        back_populates="hero_decks",
        foreign_keys=[hero_dbf_id],
    )
    card_entries: Mapped[list[DeckCardModel]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DeckCardModel(Base):
    """A card occurrence group within a deck."""

    __tablename__ = "deck_cards"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "zone IN ('main', 'sideboard')",
            name="zone_valid",
        ),
        CheckConstraint(
            "(zone = 'main' AND sideboard_owner_dbf_id IS NULL) OR "
            "(zone = 'sideboard' AND sideboard_owner_dbf_id IS NOT NULL)",
            name="zone_owner_consistent",
        ),
        Index("ix_deck_cards_deck_id", "deck_id"),
        Index("ix_deck_cards_card_dbf_id", "card_dbf_id"),
        Index("ix_deck_cards_sideboard_owner", "sideboard_owner_dbf_id"),
        Index(
            "uq_deck_cards_main_card",
            "deck_id",
            "card_dbf_id",
            unique=True,
            sqlite_where=text("zone = 'main'"),
            postgresql_where=text("zone = 'main'"),
        ),
        Index(
            "uq_deck_cards_sideboard_card_owner",
            "deck_id",
            "card_dbf_id",
            "sideboard_owner_dbf_id",
            unique=True,
            sqlite_where=text("zone = 'sideboard'"),
            postgresql_where=text("zone = 'sideboard'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"),
        nullable=False,
    )
    card_dbf_id: Mapped[int] = mapped_column(
        ForeignKey("cards.dbf_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    zone: Mapped[str] = mapped_column(String(16), nullable=False)
    sideboard_owner_dbf_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.dbf_id", ondelete="RESTRICT"),
    )

    deck: Mapped[DeckModel] = relationship(back_populates="card_entries")
    card: Mapped[CardModel] = relationship(
        back_populates="deck_entries",
        foreign_keys=[card_dbf_id],
    )
    sideboard_owner: Mapped[CardModel | None] = relationship(
        back_populates="owned_sideboard_entries",
        foreign_keys=[sideboard_owner_dbf_id],
    )
