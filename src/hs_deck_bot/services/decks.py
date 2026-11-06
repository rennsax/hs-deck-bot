"""Deck registration business logic."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import unicodedata

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hs_deck import Deck

from ..database import CardModel, DeckCardModel, DeckModel


class DeckStorageError(RuntimeError):
    """Base error for persistent deck registration."""


class DeckNameConflictError(DeckStorageError):
    """Raised when one creator already has a deck with the same name."""


class InvalidDeckNameError(DeckStorageError):
    """Raised when a deck or creator name cannot be persisted."""


@dataclass(frozen=True, slots=True)
class RegisteredDeck:
    """Summary returned after a deck has been registered."""

    id: int
    name: str
    creator_name: str
    class_name: str
    format_name: str
    card_count: int


async def register_deck(
    session: AsyncSession,
    deck: Deck,
    creator_name: str,
) -> RegisteredDeck:
    """Persist a parsed deck and return its registration summary."""

    display_deck_name = _clean_display_name(deck.name, "卡组名")
    display_creator_name = _clean_display_name(creator_name, "创建者")
    try:
        existing_id = await session.scalar(
            select(DeckModel.id).where(
                DeckModel.creator_name == display_creator_name,
                DeckModel.name == display_deck_name,
            )
        )
        if existing_id is not None:
            raise DeckNameConflictError(
                f"创建者 {display_creator_name} 已有同名卡组"
            )

        required_card_ids = {
            deck.hero.dbf_id,
            *(card.dbf_id for card in deck.cards),
            *(card.dbf_id for card in deck.sideboard_cards),
        }
        required_card_ids.update(
            card.sideboard_owner_dbf_id
            for card in deck.sideboard_cards
            if card.sideboard_owner_dbf_id is not None
        )
        existing_card_ids = set(
            (
                await session.scalars(
                    select(CardModel.dbf_id).where(
                        CardModel.dbf_id.in_(required_card_ids)
                    )
                )
            ).all()
        )
        missing_card_ids = sorted(
            required_card_ids.difference(existing_card_ids)
        )
        if missing_card_ids:
            missing = ", ".join(map(str, missing_card_ids))
            raise DeckStorageError(f"卡牌目录缺少 DBF ID：{missing}")

        deck_model = DeckModel(
            name=display_deck_name,
            creator_name=display_creator_name,
            class_key=deck.hero.card_class or "UNKNOWN",
            format_id=deck.format_id,
            hero_dbf_id=deck.hero.dbf_id,
        )
        session.add(deck_model)

        for dbf_id, quantity in Counter(
            card.dbf_id for card in deck.cards
        ).items():
            deck_model.card_entries.append(
                DeckCardModel(
                    card_dbf_id=dbf_id,
                    quantity=quantity,
                    zone="main",
                )
            )

        sideboard_counts = Counter(
            (card.dbf_id, card.sideboard_owner_dbf_id)
            for card in deck.sideboard_cards
        )
        for (dbf_id, owner_dbf_id), quantity in sideboard_counts.items():
            if owner_dbf_id is None:
                raise DeckStorageError("备选牌缺少所属卡")
            deck_model.card_entries.append(
                DeckCardModel(
                    card_dbf_id=dbf_id,
                    quantity=quantity,
                    zone="sideboard",
                    sideboard_owner_dbf_id=owner_dbf_id,
                )
            )

        await session.flush()
        return RegisteredDeck(
            id=deck_model.id,
            name=deck_model.name,
            creator_name=deck_model.creator_name,
            class_name=deck.class_name,
            format_name=deck.format_name,
            card_count=deck.card_count,
        )
    except DeckStorageError:
        raise
    except IntegrityError as error:
        if _is_deck_name_conflict(error):
            raise DeckNameConflictError(
                f"创建者 {display_creator_name} 已有同名卡组"
            ) from error
        raise DeckStorageError("卡组数据不符合数据库约束") from error
    except SQLAlchemyError as error:
        raise DeckStorageError("卡组保存失败") from error


def _clean_display_name(value: str, field_name: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value.strip())
    if not cleaned:
        raise InvalidDeckNameError(f"{field_name}不能为空")
    if len(cleaned) > 255:
        raise InvalidDeckNameError(f"{field_name}不能超过 255 个字符")
    return cleaned


def _is_deck_name_conflict(error: IntegrityError) -> bool:
    message = str(error.orig)
    return (
        "decks.creator_name, decks.name" in message
        or "uq_decks_creator_name" in message
    )
