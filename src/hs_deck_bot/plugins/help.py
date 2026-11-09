"""Show usage information for public Bot commands."""

from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.access_control import AccessRole, on_authorized_command
from hs_deck_bot.commands import handle_help_command
from hs_deck_bot.conversation_logging import public_command


help_command = on_authorized_command(
    "help",
    required_role=AccessRole.READER,
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
