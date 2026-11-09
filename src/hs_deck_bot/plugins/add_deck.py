"""Register public Hearthstone decks."""

from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.access_control import AccessRole, on_authorized_command
from hs_deck_bot.commands import handle_add_deck_command
from hs_deck_bot.conversation_logging import public_command


add_deck = on_authorized_command(
    "add-deck",
    required_role=AccessRole.WRITER,
    aliases={"添加卡组"},
    priority=10,
    block=True,
)


@add_deck.handle()
@public_command(add_deck)
async def handle_add_deck(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> str:
    return await handle_add_deck_command(args.extract_plain_text())
