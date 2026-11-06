"""Database-backed cache for the complete localized card catalog."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import logging
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hs_deck import (
    CARD_CATALOG_SCHEMA_VERSION,
    CardCatalogSnapshot,
    CardIndex,
    CardIndexError,
    CardMetadata,
    fetch_card_catalog,
)

from .models import CardCatalogStateModel, CardModel
from .session import DatabaseError, session_scope


CATALOG_STATE_ID = 1
CATALOG_TTL = timedelta(days=7)
UPSERT_BATCH_SIZE = 100

logger = logging.getLogger(__name__)


class CardCatalogError(DatabaseError):
    """Base error for database-backed card catalog operations."""


class CardCatalogUnavailableError(CardCatalogError):
    """Raised when no complete card catalog is available."""


class CardCatalogRegressionError(CardCatalogError):
    """Raised when a new catalog unexpectedly drops known DBF IDs."""


_card_index: Mapping[int, CardMetadata] | None = None
_catalog_lock: asyncio.Lock | None = None


def _get_catalog_lock() -> asyncio.Lock:
    global _catalog_lock

    if _catalog_lock is None:
        _catalog_lock = asyncio.Lock()
    return _catalog_lock


def get_card_index() -> Mapping[int, CardMetadata]:
    """Return the initialized process-local card index."""

    if _card_index is None:
        raise CardCatalogUnavailableError("卡牌目录尚未初始化")
    return _card_index


def clear_card_index() -> None:
    """Clear process-local card catalog state."""

    global _card_index, _catalog_lock
    _card_index = None
    _catalog_lock = None


async def initialize_card_catalog() -> None:
    """Load the catalog from SQLite and refresh it when it is stale."""

    global _card_index

    async with _get_catalog_lock():
        invalid_stored_catalog: CardCatalogUnavailableError | None = None
        try:
            async with session_scope() as session:
                state, stored_index = await _load_stored_catalog(session)
        except CardCatalogUnavailableError as error:
            logger.warning("数据库中的卡牌目录不可用，将尝试重新下载：%s", error)
            invalid_stored_catalog = error
            state, stored_index = None, {}

        if state is not None and _is_fresh(state.fetched_at):
            _card_index = _freeze_index(stored_index)
            return

        try:
            snapshot = await asyncio.to_thread(fetch_card_catalog)
        except CardIndexError as error:
            if state is not None:
                logger.warning("卡牌目录刷新失败，继续使用旧数据：%s", error)
                _card_index = _freeze_index(stored_index)
                return
            reason = (
                f"；数据库目录无效：{invalid_stored_catalog}"
                if invalid_stored_catalog is not None
                else ""
            )
            raise CardCatalogUnavailableError(
                f"无法下载卡牌目录，且数据库中没有可用旧数据{reason}"
            ) from error

        async with session_scope() as session:
            await sync_card_catalog(session, snapshot)
        _card_index = _freeze_index(snapshot.index)


async def sync_card_catalog(
    session: AsyncSession,
    snapshot: CardCatalogSnapshot,
) -> None:
    """Atomically upsert one validated catalog snapshot."""

    _validate_snapshot(snapshot)
    existing_ids = set(
        (await session.scalars(select(CardModel.dbf_id))).all()
    )
    incoming_ids = set(snapshot.index)
    missing_ids = sorted(existing_ids.difference(incoming_ids))
    if missing_ids:
        preview = ", ".join(map(str, missing_ids[:20]))
        suffix = "..." if len(missing_ids) > 20 else ""
        raise CardCatalogRegressionError(
            "新卡牌目录缺少数据库中的 DBF ID："
            f"{preview}{suffix}（共 {len(missing_ids)} 张）"
        )

    rows = [_card_row(card) for card in snapshot.cards]
    for batch in _batched(rows, UPSERT_BATCH_SIZE):
        statement = sqlite_insert(CardModel).values(batch)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[CardModel.dbf_id],
            set_={
                "card_id": excluded.card_id,
                "name": excluded.name,
                "cost": excluded.cost,
                "card_type": excluded.card_type,
                "card_class": excluded.card_class,
                "collectible": excluded.collectible,
                "raw_metadata": excluded.raw_metadata,
            },
        )
        await session.execute(statement)

    state_statement = sqlite_insert(CardCatalogStateModel).values(
        id=CATALOG_STATE_ID,
        schema_version=snapshot.schema_version,
        source_url=snapshot.source_url,
        fetched_at=snapshot.fetched_at,
        card_count=len(snapshot.cards),
    )
    state_statement = state_statement.on_conflict_do_update(
        index_elements=[CardCatalogStateModel.id],
        set_={
            "schema_version": state_statement.excluded.schema_version,
            "source_url": state_statement.excluded.source_url,
            "fetched_at": state_statement.excluded.fetched_at,
            "card_count": state_statement.excluded.card_count,
        },
    )
    await session.execute(state_statement)


async def _load_stored_catalog(
    session: AsyncSession,
) -> tuple[CardCatalogStateModel | None, CardIndex]:
    state = await session.get(CardCatalogStateModel, CATALOG_STATE_ID)
    rows = (
        await session.execute(
            select(
                CardModel.dbf_id,
                CardModel.card_id,
                CardModel.name,
                CardModel.cost,
                CardModel.card_type,
                CardModel.card_class,
                CardModel.collectible,
                CardModel.raw_metadata,
            )
        )
    ).all()
    index: CardIndex = {}
    for row in rows:
        metadata = row.raw_metadata
        if not isinstance(metadata, dict):
            raise CardCatalogUnavailableError(
                f"卡牌 {row.dbf_id} 的 raw_metadata 不是 JSON 对象"
            )
        try:
            expected = _card_row(metadata)
        except (KeyError, TypeError) as error:
            raise CardCatalogUnavailableError(
                f"卡牌 {row.dbf_id} 的 raw_metadata 缺少核心字段"
            ) from error
        stored = {
            "dbf_id": row.dbf_id,
            "card_id": row.card_id,
            "name": row.name,
            "cost": row.cost,
            "card_type": row.card_type,
            "card_class": row.card_class,
            "collectible": row.collectible,
        }
        if any(stored[key] != expected[key] for key in stored):
            raise CardCatalogUnavailableError(
                f"卡牌 {row.dbf_id} 的常用列与 raw_metadata 不一致"
            )
        index[row.dbf_id] = metadata

    if state is None and not index:
        return None, {}
    if state is None:
        raise CardCatalogUnavailableError("卡牌目录缺少状态记录")
    if state.schema_version != CARD_CATALOG_SCHEMA_VERSION:
        raise CardCatalogUnavailableError(
            "卡牌目录 schema 版本不兼容："
            f"数据库 {state.schema_version}，程序 {CARD_CATALOG_SCHEMA_VERSION}"
        )

    actual_count = len(index)
    if actual_count != state.card_count or len(index) != state.card_count:
        raise CardCatalogUnavailableError(
            "卡牌目录数量与状态记录不一致："
            f"状态 {state.card_count}，实际 {actual_count}"
        )
    return state, index


def _is_fresh(fetched_at: datetime) -> bool:
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc) < CATALOG_TTL


def _freeze_index(index: Mapping[int, CardMetadata]) -> Mapping[int, CardMetadata]:
    return MappingProxyType(
        {
            dbf_id: _freeze_mapping(metadata)
            for dbf_id, metadata in index.items()
        }
    )


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {key: _freeze_value(item) for key, item in value.items()}
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, dict):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _card_row(card: CardMetadata) -> dict[str, object]:
    return {
        "dbf_id": card["dbfId"],
        "card_id": card["id"],
        "name": card["name"],
        "cost": card.get("cost") if isinstance(card.get("cost"), int) else None,
        "card_type": card.get("type") if isinstance(card.get("type"), str) else None,
        "card_class": (
            card.get("cardClass")
            if isinstance(card.get("cardClass"), str)
            else None
        ),
        "collectible": (
            card.get("collectible")
            if isinstance(card.get("collectible"), bool)
            else None
        ),
        "raw_metadata": dict(card),
    }


def _validate_snapshot(snapshot: CardCatalogSnapshot) -> None:
    if snapshot.schema_version != CARD_CATALOG_SCHEMA_VERSION:
        raise CardCatalogError(
            "卡牌目录 schema 版本不兼容："
            f"快照 {snapshot.schema_version}，程序 {CARD_CATALOG_SCHEMA_VERSION}"
        )
    if not snapshot.cards or len(snapshot.cards) != len(snapshot.index):
        raise CardCatalogError("卡牌目录快照数量不一致或为空")

    dbf_ids: set[int] = set()
    card_ids: set[str] = set()
    for card in snapshot.cards:
        dbf_id = card.get("dbfId")
        card_id = card.get("id")
        name = card.get("name")
        if not isinstance(dbf_id, int) or isinstance(dbf_id, bool):
            raise CardCatalogError("卡牌目录快照包含无效 DBF ID")
        if not isinstance(card_id, str) or not card_id:
            raise CardCatalogError(f"卡牌 {dbf_id} 缺少 card ID")
        if not isinstance(name, str) or not name:
            raise CardCatalogError(f"卡牌 {dbf_id} 缺少中文名称")
        if dbf_id in dbf_ids or card_id in card_ids:
            raise CardCatalogError("卡牌目录快照包含重复 DBF ID 或 card ID")
        if snapshot.index.get(dbf_id) != card:
            raise CardCatalogError(f"卡牌 {dbf_id} 与快照索引不一致")
        dbf_ids.add(dbf_id)
        card_ids.add(card_id)


def _batched(
    values: Sequence[dict[str, object]],
    size: int,
) -> Iterator[Sequence[dict[str, object]]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]
