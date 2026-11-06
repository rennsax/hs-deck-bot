"""Command-line frontend for the Hearthstone deck Bot application."""

from __future__ import annotations

import argparse
import asyncio
import sys

from nonebot.config import Config, Env

from .commands import execute_command
from .database import (
    DatabaseConfigError,
    DatabaseError,
    clear_card_index,
    configure_database,
    dispose_database,
    initialize_card_catalog,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用与 NoneBot 相同的命令访问炉石卡组数据库",
    )
    parser.add_argument(
        "--database-url",
        help="覆盖 HS_DECK_DATABASE_URL",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="要执行的命令；省略时进入交互模式",
    )
    return parser.parse_args()


async def _run(command_parts: list[str]) -> int:
    try:
        await initialize_card_catalog()
        if command_parts:
            print(await execute_command(" ".join(command_parts)))
        else:
            await _interactive_console()
        return 0
    except DatabaseError as error:
        print(f"数据库初始化失败：{error}", file=sys.stderr)
        return 1
    finally:
        clear_card_index()
        await dispose_database()


async def _interactive_console() -> None:
    if sys.stdin.isatty():
        print("hs-deck-bot 命令行界面；输入 exit 或 quit 退出。")

    while True:
        try:
            line = input("> " if sys.stdin.isatty() else "")
        except EOFError:
            break

        stripped = line.strip()
        if stripped in {"exit", "quit"}:
            break
        if not stripped:
            continue
        print(await execute_command(stripped))


def main() -> int:
    args = _parse_args()
    database_url = _load_database_url(args.database_url)
    if database_url is None:
        print(
            "数据库初始化失败：请设置 HS_DECK_DATABASE_URL，"
            "或使用 --database-url 指定数据库地址。",
            file=sys.stderr,
        )
        return 2

    try:
        configure_database(database_url)
        return asyncio.run(_run(args.command))
    except DatabaseConfigError as error:
        print(f"数据库初始化失败：{error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def _load_database_url(override: str | None) -> str | None:
    if override is not None:
        return override

    environment = Env()
    config = Config(
        _env_file=(".env", f".env.{environment.environment}"),
    )
    database_url = getattr(config, "hs_deck_database_url", None)
    return str(database_url) if database_url is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
