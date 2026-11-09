"""Group and private-user authorization for public QQ commands."""

from __future__ import annotations

from enum import IntEnum
import json
from typing import Any

from nonebot import get_plugin_config, logger, on_command
from nonebot.adapters import Bot, Event
from nonebot.consts import (
    CMD_ARG_KEY,
    CMD_KEY,
    CMD_WHITESPACE_KEY,
    RAW_CMD_KEY,
)
from nonebot.matcher import Matcher
from nonebot.permission import Permission
from nonebot.rule import TrieRule
from pydantic import BaseModel, Field, field_validator, model_validator


class AccessRole(IntEnum):
    """Access levels granted to QQ groups and private users."""

    UNAUTHORIZED = 0
    READER = 1
    WRITER = 2


class AccessConfig(BaseModel):
    """Configured QQ OpenIDs for read and write access."""

    hs_deck_writer_group_openids: frozenset[str] = Field(
        default_factory=frozenset
    )
    hs_deck_reader_group_openids: frozenset[str] = Field(
        default_factory=frozenset
    )
    hs_deck_writer_user_openids: frozenset[str] = Field(
        default_factory=frozenset
    )
    hs_deck_reader_user_openids: frozenset[str] = Field(
        default_factory=frozenset
    )

    @field_validator(
        "hs_deck_writer_group_openids",
        "hs_deck_reader_group_openids",
        "hs_deck_writer_user_openids",
        "hs_deck_reader_user_openids",
    )
    @classmethod
    def validate_openids(
        cls,
        openids: frozenset[str],
    ) -> frozenset[str]:
        if any(not value or value != value.strip() for value in openids):
            raise ValueError("OpenIDs must be non-empty and unpadded")
        return openids

    @model_validator(mode="after")
    def validate_distinct_roles(self) -> AccessConfig:
        group_overlap = (
            self.hs_deck_writer_group_openids
            & self.hs_deck_reader_group_openids
        )
        if group_overlap:
            raise ValueError(
                "writer and reader group OpenIDs must not overlap"
            )
        user_overlap = (
            self.hs_deck_writer_user_openids
            & self.hs_deck_reader_user_openids
        )
        if user_overlap:
            raise ValueError(
                "writer and reader user OpenIDs must not overlap"
            )
        return self


access_config = get_plugin_config(AccessConfig)


def resolve_group_role(
    group_openid: str | None,
    config: AccessConfig = access_config,
) -> AccessRole:
    """Resolve one QQ group OpenID to its configured role."""

    if group_openid in config.hs_deck_writer_group_openids:
        return AccessRole.WRITER
    if group_openid in config.hs_deck_reader_group_openids:
        return AccessRole.READER
    return AccessRole.UNAUTHORIZED


def resolve_user_role(
    user_openid: str | None,
    config: AccessConfig = access_config,
) -> AccessRole:
    """Resolve one QQ private user OpenID to its configured role."""

    if user_openid in config.hs_deck_writer_user_openids:
        return AccessRole.WRITER
    if user_openid in config.hs_deck_reader_user_openids:
        return AccessRole.READER
    return AccessRole.UNAUTHORIZED


def resolve_event_role(
    event: Event,
    config: AccessConfig = access_config,
) -> AccessRole:
    """Resolve a group or private QQ message event to its access role."""

    group_openid = getattr(event, "group_openid", None)
    if group_openid is not None:
        return resolve_group_role(group_openid, config)

    author = getattr(event, "author", None)
    user_openid = getattr(author, "user_openid", None)
    if user_openid is not None:
        return resolve_user_role(user_openid, config)

    return AccessRole.UNAUTHORIZED


def has_required_role(actual: AccessRole, required: AccessRole) -> bool:
    """Return whether an actual access role meets a command requirement."""

    return actual >= required


def on_authorized_command(
    cmd: str | tuple[str, ...],
    *,
    required_role: AccessRole,
    **kwargs: Any,
) -> type[Matcher]:
    """Register a command protected by an explicit QQ access role."""

    if required_role not in (AccessRole.READER, AccessRole.WRITER):
        raise ValueError("commands must require the reader or writer role")
    if "permission" in kwargs:
        raise ValueError("command permission is managed by access authorization")

    commands = {cmd, *(kwargs.get("aliases") or set())}
    return on_command(
        cmd,
        permission=_access_permission(
            required_role,
            commands=frozenset(
                (command,) if isinstance(command, str) else command
                for command in commands
            ),
            force_whitespace=kwargs.get("force_whitespace"),
        ),
        **kwargs,
    )


def _access_permission(
    required_role: AccessRole,
    *,
    commands: frozenset[tuple[str, ...]],
    force_whitespace: str | bool | None,
) -> Permission:
    async def check_access(bot: Bot, event: Event) -> bool:
        matches_command, command = _event_command_match(
            bot,
            event,
            commands=commands,
            force_whitespace=force_whitespace,
        )
        if not matches_command:
            return False

        group_openid = getattr(event, "group_openid", None)
        actual_role = resolve_event_role(event)
        if has_required_role(actual_role, required_role):
            return True

        logger.warning(
            _format_authorization_record(
                event,
                group_openid=group_openid,
                actual_role=actual_role,
                required_role=required_role,
                command=command,
            )
        )
        return False

    return Permission(check_access)


def _event_command_match(
    bot: Bot,
    event: Event,
    *,
    commands: frozenset[tuple[str, ...]],
    force_whitespace: str | bool | None,
) -> tuple[bool, str]:
    try:
        prefix = TrieRule.get_value(bot, event, {})
    except Exception:
        return False, ""
    if prefix[CMD_KEY] not in commands:
        return False, ""

    raw_command = prefix[RAW_CMD_KEY] or ""
    command_arg = prefix[CMD_ARG_KEY]
    if force_whitespace is None or not command_arg:
        return True, raw_command
    if isinstance(force_whitespace, str):
        return (
            force_whitespace == prefix[CMD_WHITESPACE_KEY],
            raw_command,
        )
    return (
        force_whitespace == (prefix[CMD_WHITESPACE_KEY] is not None),
        raw_command,
    )


def _format_authorization_record(
    event: Event,
    *,
    group_openid: object,
    actual_role: AccessRole,
    required_role: AccessRole,
    command: str,
) -> str:
    record = {
        "status": "denied",
        "event_type": event.get_event_name(),
        "scene": _event_scene(event),
        "group_openid": group_openid,
        "user_id": _event_user_id(event),
        "command": command,
        "required_role": required_role.name.lower(),
        "actual_role": actual_role.name.lower(),
    }
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    return f"AUTHORIZATION {payload}"


def _event_scene(event: Event) -> str:
    if getattr(event, "group_openid", None):
        return "group"
    if getattr(event, "guild_id", None):
        return "guild"
    return "c2c"


def _event_user_id(event: Event) -> str:
    try:
        return event.get_user_id()
    except Exception:
        return "未知用户"
