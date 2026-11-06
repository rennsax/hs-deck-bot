"""Async database engine and transaction management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from nonebot import get_driver
from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseError(RuntimeError):
    """Base error for database configuration and transaction failures."""


class DatabaseConfigError(DatabaseError):
    """Raised when the configured database URL is missing or unsupported."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_database_url_override: str | None = None


def configure_database(database_url: str) -> None:
    """Configure a database URL for non-NoneBot application frontends."""

    global _database_url_override

    if _engine is not None:
        raise DatabaseConfigError("数据库连接已创建，不能再修改数据库地址")
    _database_url_override = _normalize_database_url(database_url)


def _get_database_url() -> str:
    if _database_url_override is not None:
        return _database_url_override

    try:
        database_url = getattr(
            get_driver().config,
            "hs_deck_database_url",
            None,
        )
    except ValueError as error:
        raise DatabaseConfigError(
            "HS_DECK_DATABASE_URL 未配置，且 NoneBot 尚未初始化"
        ) from error
    if not database_url:
        raise DatabaseConfigError("HS_DECK_DATABASE_URL 未配置")

    return _normalize_database_url(str(database_url))


def _normalize_database_url(database_url: str) -> str:
    normalized_url = database_url.strip()
    if not normalized_url:
        raise DatabaseConfigError("HS_DECK_DATABASE_URL 不能为空")

    try:
        parsed_url: URL = make_url(normalized_url)
    except ArgumentError as error:
        raise DatabaseConfigError("HS_DECK_DATABASE_URL 格式无效") from error
    if parsed_url.drivername != "sqlite+aiosqlite":
        raise DatabaseConfigError(
            "HS_DECK_DATABASE_URL 必须使用 sqlite+aiosqlite 驱动"
        )
    return normalized_url


def _get_engine() -> AsyncEngine:
    global _engine, _session_factory

    if _engine is None:
        _engine = create_async_engine(_get_database_url())

        @event.listens_for(_engine.sync_engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    _get_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Provide one session and one transaction for a database operation."""

    try:
        async with _get_session_factory()() as session:
            async with session.begin():
                yield session
    except DatabaseError:
        raise
    except SQLAlchemyError as error:
        raise DatabaseError("数据库事务执行失败") from error


async def dispose_database() -> None:
    """Close pooled connections created by the application."""

    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
