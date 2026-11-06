"""Shared command behavior for NoneBot plugins and the command-line UI."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import unicodedata

from hs_deck import (
    CardIndexError,
    CardNotFoundError,
    Deck,
    DeckCodeError,
    HsDeckError,
)

from .database import (
    CardCatalogError,
    DatabaseError,
    get_card_index,
    session_scope,
)
from .services import (
    DeletedDeck,
    DeckNameConflictError,
    DeckNotFoundError,
    DeckSearchResult,
    DeckStorageError,
    InvalidDeckNameError,
    RegisteredDeck,
    delete_deck,
    register_deck,
    search_decks,
)


DECK_USAGE = "用法：/卡组 <卡组代码>"
ADD_DECK_USAGE = "用法：/添加卡组 <卡组名> <创建者> <卡组代码>"
DELETE_DECK_USAGE = "用法：/删卡组 <卡组名> <创建者>"
SEARCH_DECK_USAGE = "用法：/找卡组 <卡组名>"
UNKNOWN_COMMAND = (
    "未知命令。支持的命令：/卡组、/添加卡组、/删卡组、/找卡组"
)

logger = logging.getLogger(__name__)


async def handle_deck_command(raw_args: str) -> str:
    """Execute `/deck` and return its user-facing response."""

    deck_code = raw_args.strip()
    if not deck_code:
        return DECK_USAGE

    try:
        parsed_deck = await asyncio.to_thread(
            Deck.from_code,
            deck_code,
            "炉石卡组",
            card_index=get_card_index(),
        )
        return str(parsed_deck)
    except CardCatalogError:
        logger.exception("处理 /deck 命令时卡牌目录不可用")
        return "卡牌数据暂时无法加载，请稍后重试。"
    except HsDeckError as error:
        return _deck_error_message(error)
    except Exception:
        logger.exception("处理 /deck 命令时发生未预期错误")
        return "卡组查询失败，请稍后重试。"


async def handle_add_deck_command(raw_args: str) -> str:
    """Execute `/add-deck` and return its user-facing response."""

    parsed_args = _parse_add_deck_args(raw_args)
    if parsed_args is None:
        return ADD_DECK_USAGE

    deck_name, creator_name, deck_code = parsed_args
    if len(deck_name) > 255 or len(creator_name) > 255:
        return "卡组名和创建者均不能超过 255 个字符。"

    try:
        parsed_deck = await asyncio.to_thread(
            Deck.from_code,
            deck_code,
            deck_name,
            card_index=get_card_index(),
        )
        async with session_scope() as session:
            result = await register_deck(
                session,
                parsed_deck,
                creator_name,
            )
        return _add_deck_success_message(result)
    except CardCatalogError:
        logger.exception("处理 /add-deck 命令时卡牌目录不可用")
        return "卡牌数据暂时无法加载，请稍后重试。"
    except HsDeckError as error:
        return _add_deck_error_message(error)
    except DeckNameConflictError:
        return f"创建者「{creator_name}」已经注册过卡组「{deck_name}」。"
    except InvalidDeckNameError as error:
        return str(error)
    except (DeckStorageError, DatabaseError):
        logger.exception("保存 /add-deck 卡组时发生数据库错误")
        return "卡组保存失败，请稍后重试。"
    except Exception:
        logger.exception("处理 /add-deck 命令时发生未预期错误")
        return "卡组注册失败，请稍后重试。"


async def handle_search_deck_command(raw_args: str) -> str:
    """Execute `/search-deck` and return its user-facing response."""

    query = unicodedata.normalize("NFKC", raw_args.strip())
    if not query:
        return SEARCH_DECK_USAGE
    if len(query) > 255:
        return "卡组名不能超过 255 个字符。"

    try:
        async with session_scope() as session:
            results = await search_decks(session, query)
    except (DeckStorageError, DatabaseError):
        logger.exception("处理 /search-deck 命令时发生数据库错误")
        return "卡组查询失败，请稍后重试。"
    except Exception:
        logger.exception("处理 /search-deck 命令时发生未预期错误")
        return "卡组查询失败，请稍后重试。"

    if not results:
        return f"没有找到名称匹配「{query}」的卡组。"
    return _search_deck_success_message(results)


async def handle_delete_deck_command(raw_args: str) -> str:
    """Execute `/delete-deck` and return its user-facing response."""

    parsed_args = _parse_delete_deck_args(raw_args)
    if parsed_args is None:
        return DELETE_DECK_USAGE

    deck_name, creator_name = parsed_args
    if len(deck_name) > 255 or len(creator_name) > 255:
        return "卡组名和创建者均不能超过 255 个字符。"

    try:
        async with session_scope() as session:
            result = await delete_deck(session, deck_name, creator_name)
        return _delete_deck_success_message(result)
    except DeckNotFoundError:
        return f"没有找到创建者「{creator_name}」的卡组「{deck_name}」。"
    except InvalidDeckNameError as error:
        return str(error)
    except (DeckStorageError, DatabaseError):
        logger.exception("处理 /delete-deck 命令时发生数据库错误")
        return "卡组删除失败，请稍后重试。"
    except Exception:
        logger.exception("处理 /delete-deck 命令时发生未预期错误")
        return "卡组删除失败，请稍后重试。"


CommandHandler = Callable[[str], Awaitable[str]]

COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "/deck": handle_deck_command,
    "/卡组": handle_deck_command,
    "/add-deck": handle_add_deck_command,
    "/添加卡组": handle_add_deck_command,
    "/delete-deck": handle_delete_deck_command,
    "/删卡组": handle_delete_deck_command,
    "/search-deck": handle_search_deck_command,
    "/找卡组": handle_search_deck_command,
}


async def execute_command(command_line: str) -> str:
    """Execute one Bot-style command line."""

    parts = command_line.strip().split(maxsplit=1)
    if not parts:
        return UNKNOWN_COMMAND

    command = parts[0]
    raw_args = parts[1] if len(parts) == 2 else ""
    handler = COMMAND_HANDLERS.get(command)
    if handler is None:
        return UNKNOWN_COMMAND
    return await handler(raw_args)


def _parse_add_deck_args(raw_args: str) -> tuple[str, str, str] | None:
    parts = raw_args.split()
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def _parse_delete_deck_args(raw_args: str) -> tuple[str, str] | None:
    parts = raw_args.split()
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _deck_error_message(error: HsDeckError) -> str:
    if isinstance(error, DeckCodeError):
        return "卡组代码无效，请检查后重试。"
    if isinstance(error, CardNotFoundError):
        return "卡牌数据尚未更新，暂时无法解析这副卡组。"
    if isinstance(error, CardIndexError):
        return "卡牌数据暂时无法加载，请稍后重试。"
    return "卡组查询失败，请稍后重试。"


def _add_deck_error_message(error: HsDeckError) -> str:
    if isinstance(error, DeckCodeError):
        return "卡组代码无效，请检查后重试。"
    if isinstance(error, CardNotFoundError):
        return "卡牌数据尚未更新，暂时无法注册这副卡组。"
    if isinstance(error, CardIndexError):
        return "卡牌数据暂时无法加载，请稍后重试。"
    return "卡组解析失败，请稍后重试。"


def _add_deck_success_message(result: RegisteredDeck) -> str:
    return "\n".join(
        [
            f"已添加卡组「{result.name}」",
            f"创建者：{result.creator_name}",
            f"职业：{result.class_name}",
            f"模式：{result.format_name}",
            f"主牌数量：{result.card_count}",
        ]
    )


def _delete_deck_success_message(result: DeletedDeck) -> str:
    return (
        f"已删除「{result.creator_name}」创建的卡组「{result.name}」，"
        "误操作请使用 "
        f"`/添加卡组 {result.name} {result.creator_name} {result.deck_code}` 恢复。"
    )


def _search_deck_success_message(
    results: tuple[DeckSearchResult, ...],
) -> str:
    blocks = [f"找到 {len(results)} 套匹配卡组："]
    blocks.extend(
        "\n".join(
            [
                f"{index}. 卡组名：{result.name}",
                f"创建者：{result.creator_name}",
                f"卡组代码：{result.deck_code}",
            ]
        )
        for index, result in enumerate(results, start=1)
    )
    return "\n\n".join(blocks)
