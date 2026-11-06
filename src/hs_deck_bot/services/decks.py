"""Deck storage business logic."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import unicodedata

from manacost_deckstrings import DeckstringError, encode
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hs_deck import Deck

from ..database import CardModel, DeckCardModel, DeckModel


SEARCH_RESULT_LIMIT = 5
SEARCH_SCORE_CUTOFF = 60.0


class DeckStorageError(RuntimeError):
    """Base error for persistent deck registration."""


class DeckNameConflictError(DeckStorageError):
    """Raised when one creator already has a deck with the same name."""


class DeckNotFoundError(DeckStorageError):
    """Raised when a deck cannot be found by creator and deck name."""


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


@dataclass(frozen=True, slots=True)
class DeckSearchResult:
    """One registered deck returned by a name search."""

    id: int
    name: str
    creator_name: str
    created_at: datetime
    deck_code: str


@dataclass(frozen=True, slots=True)
class DeletedDeck:
    """A deleted deck and the code needed to restore it."""

    id: int
    name: str
    creator_name: str
    deck_code: str


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


async def search_decks(
    session: AsyncSession,
    query: str,
    *,
    limit: int = SEARCH_RESULT_LIMIT,
    score_cutoff: float = SEARCH_SCORE_CUTOFF,
) -> tuple[DeckSearchResult, ...]:
    """Find registered decks by fuzzy-matching their display names."""

    candidate_rows = (
        await session.execute(
            select(
                DeckModel.id,
                DeckModel.name,
                DeckModel.creator_name,
            ).order_by(DeckModel.id)
        )
    ).all()
    choices = {
        deck_id: name
        for deck_id, name, _creator_name in candidate_rows
    }
    matched_ids = _find_deck_ids(
        query,
        choices,
        limit=limit,
        score_cutoff=score_cutoff,
    )
    if not matched_ids:
        return ()

    matched_decks = (
        await session.scalars(
            select(DeckModel)
            .where(DeckModel.id.in_(matched_ids))
            .options(selectinload(DeckModel.card_entries))
        )
    ).all()
    decks_by_id = {deck.id: deck for deck in matched_decks}
    try:
        return tuple(
            DeckSearchResult(
                id=deck_id,
                name=decks_by_id[deck_id].name,
                creator_name=decks_by_id[deck_id].creator_name,
                created_at=_as_utc(decks_by_id[deck_id].created_at),
                deck_code=_encode_stored_deck(decks_by_id[deck_id]),
            )
            for deck_id in matched_ids
        )
    except KeyError as error:
        raise DeckStorageError("卡组在查询期间发生变化，请重试") from error


async def delete_deck(
    session: AsyncSession,
    deck_name: str,
    creator_name: str,
) -> DeletedDeck:
    """Delete one exactly matched deck and return its recovery code."""

    display_deck_name = _clean_display_name(deck_name, "卡组名")
    display_creator_name = _clean_display_name(creator_name, "创建者")
    try:
        deck = (
            await session.execute(
                select(DeckModel)
                .where(
                    DeckModel.creator_name == display_creator_name,
                    DeckModel.name == display_deck_name,
                )
                .options(selectinload(DeckModel.card_entries))
            )
        ).scalar_one_or_none()
        if deck is None:
            raise DeckNotFoundError(
                f"未找到创建者 {display_creator_name} 的卡组 {display_deck_name}"
            )

        deleted_deck = DeletedDeck(
            id=deck.id,
            name=deck.name,
            creator_name=deck.creator_name,
            deck_code=_encode_stored_deck(deck),
        )
        await session.delete(deck)
        await session.flush()
        return deleted_deck
    except DeckStorageError:
        raise
    except SQLAlchemyError as error:
        raise DeckStorageError("卡组删除失败") from error


def _find_deck_ids(
    query: str,
    choices: Mapping[int, str],
    *,
    limit: int = SEARCH_RESULT_LIMIT,
    score_cutoff: float = SEARCH_SCORE_CUTOFF,
) -> tuple[int, ...]:
    matches = process.extract(
        query,
        choices,
        scorer=fuzz.WRatio,
        processor=_normalize_search_text,
        limit=limit,
        score_cutoff=score_cutoff,
    )
    return tuple(match[2] for match in matches)


def _normalize_search_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _encode_stored_deck(deck: DeckModel) -> str:
    main_cards: list[list[int]] = []
    sideboard_cards: list[list[int]] = []
    for entry in deck.card_entries:
        if entry.zone == "main":
            main_cards.append([entry.card_dbf_id, entry.quantity])
            continue
        if entry.zone != "sideboard" or entry.sideboard_owner_dbf_id is None:
            raise DeckStorageError(f"卡组 {deck.id} 包含无效卡牌区域")
        sideboard_cards.append(
            [
                entry.card_dbf_id,
                entry.quantity,
                entry.sideboard_owner_dbf_id,
            ]
        )

    try:
        return encode(
            {
                "format": deck.format_id,
                "heroes": [deck.hero_dbf_id],
                "cards": main_cards,
                "sideboardCards": sideboard_cards,
            }
        )
    except DeckstringError as error:
        raise DeckStorageError(
            f"无法从数据库重建卡组 {deck.id} 的代码"
        ) from error


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
