"""Structured console logging for public QQ command conversations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
import json
from typing import NoReturn

from nonebot import logger
from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.matcher import Matcher


CommandHandler = Callable[[Bot, MessageEvent, Message], Awaitable[str]]


def public_command(
    matcher: type[Matcher],
) -> Callable[[CommandHandler], CommandHandler]:
    """Decorate a public command handler with reply and logging behavior."""

    def decorator(handler: CommandHandler) -> CommandHandler:
        @wraps(handler)
        async def wrapped(
            bot: Bot,
            event: MessageEvent,
            args: Message,
        ) -> NoReturn:
            context = _conversation_context(bot, event)
            logger.info(_format_conversation_record(_inbound_record(context)))

            try:
                response = await handler(bot, event, args)
            except Exception as error:
                logger.error(
                    _format_conversation_record(
                        _failed_outbound_record(
                            context,
                            stage="handler",
                            error=error,
                        )
                    )
                )
                raise

            try:
                result = await matcher.send(response)
            except Exception as error:
                logger.error(
                    _format_conversation_record(
                        _failed_outbound_record(
                            context,
                            stage="send",
                            error=error,
                            content=response,
                        )
                    )
                )
                raise

            logger.info(
                _format_conversation_record(
                    _sent_outbound_record(
                        context,
                        content=response,
                        message_id=getattr(result, "id", None),
                    )
                )
            )
            await matcher.finish()

        return wrapped

    return decorator


def _format_conversation_record(record: Mapping[str, object]) -> str:
    """Encode one conversation record as a single console line."""

    payload = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"CONVERSATION {payload}"


def _conversation_context(bot: Bot, event: MessageEvent) -> dict[str, object]:
    author = getattr(event, "author", None)
    user_id = _event_user_id(event, author)
    message_id = str(
        getattr(event, "id", None)
        or getattr(event, "event_id", None)
        or event.get_session_id()
    )
    content = event.get_message().extract_plain_text()
    context: dict[str, object] = {
        "conversation_id": message_id,
        "inbound_message_id": message_id,
        "event_type": event.get_event_name(),
        "scene": _event_scene(event),
        "user_name": getattr(author, "username", None) or "未知用户",
        "user_id": user_id,
        "platform_user_id": getattr(author, "id", None),
        "bot_name": _bot_name(bot),
        "bot_id": bot.self_id,
        "command": content.strip().split(maxsplit=1)[0] if content.strip() else "",
        "content": content,
    }
    if group_openid := getattr(event, "group_openid", None):
        context["group_openid"] = group_openid
    return context


def _event_user_id(event: MessageEvent, author: object) -> str:
    try:
        return event.get_user_id()
    except Exception:
        for field in ("user_openid", "member_openid", "id"):
            value = getattr(author, field, None)
            if value:
                return str(value)
    return "未知用户"


def _bot_name(bot: Bot) -> str:
    try:
        return bot.self_info.username or "未知机器人"
    except RuntimeError:
        return "未知机器人"


def _event_scene(event: MessageEvent) -> str:
    if getattr(event, "group_openid", None):
        return "group"
    if getattr(event, "guild_id", None):
        return "guild"
    return "c2c"


def _inbound_record(context: Mapping[str, object]) -> dict[str, object]:
    record = _common_record(context)
    record.update(
        {
            "direction": "inbound",
            "message_id": context["inbound_message_id"],
            "sender_name": context["user_name"],
            "sender_id": context["user_id"],
            "recipient_name": context["bot_name"],
            "recipient_id": context["bot_id"],
            "content": context["content"],
        }
    )
    return record


def _sent_outbound_record(
    context: Mapping[str, object],
    *,
    content: str,
    message_id: object,
) -> dict[str, object]:
    record = _outbound_record(context, content=content)
    record.update(
        {
            "message_id": str(message_id) if message_id is not None else None,
            "status": "sent",
        }
    )
    return record


def _failed_outbound_record(
    context: Mapping[str, object],
    *,
    stage: str,
    error: Exception,
    content: str | None = None,
) -> dict[str, object]:
    record = _outbound_record(context, content=content)
    record.update(
        {
            "message_id": None,
            "status": "failed",
            "failure_stage": stage,
            "error_type": type(error).__name__,
            "error": str(error),
        }
    )
    return record


def _outbound_record(
    context: Mapping[str, object],
    *,
    content: str | None,
) -> dict[str, object]:
    record = _common_record(context)
    record.update(
        {
            "direction": "outbound",
            "in_reply_to": context["inbound_message_id"],
            "sender_name": context["bot_name"],
            "sender_id": context["bot_id"],
            "recipient_name": context["user_name"],
            "recipient_id": context["user_id"],
            "content": content,
        }
    )
    return record


def _common_record(context: Mapping[str, object]) -> dict[str, object]:
    record = {
        "conversation_id": context["conversation_id"],
        "event_type": context["event_type"],
        "scene": context["scene"],
        "command": context["command"],
    }
    if "group_openid" in context:
        record["group_openid"] = context["group_openid"]
    if context.get("platform_user_id"):
        record["platform_user_id"] = context["platform_user_id"]
    return record
