"""Show usage information for public Bot commands."""

from nonebot import on_command
from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_help_command
from hs_deck_bot.conversation_logging import public_command


help_command = on_command(
    "help",
    aliases={"用法"},
    priority=10,
    block=True,
)


@help_command.handle()
@public_command(help_command)
async def handle_help(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> str:
    return await handle_help_command(args.extract_plain_text())
