"""Shared command behavior for NoneBot plugins and the command-line UI."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging

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
    DeckNameConflictError,
    DeckStorageError,
    InvalidDeckNameError,
    RegisteredDeck,
    register_deck,
)


DECK_USAGE = "用法：/deck <卡组代码>"
ADD_DECK_USAGE = "用法：/add-deck <卡组名> <创建者> <卡组代码>"
UNKNOWN_COMMAND = "未知命令。支持的命令：/deck、/add-deck"

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


CommandHandler = Callable[[str], Awaitable[str]]

COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "/deck": handle_deck_command,
    "/add-deck": handle_add_deck_command,
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
