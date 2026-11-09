"""List registered public Hearthstone decks."""

from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.access_control import AccessRole, on_authorized_command
from hs_deck_bot.commands import handle_list_deck_command
from hs_deck_bot.conversation_logging import public_command


list_deck = on_authorized_command(
    "list-deck",
    required_role=AccessRole.READER,
    aliases={"所有卡组"},
    priority=10,
    block=True,
)


@list_deck.handle()
@public_command(list_deck)
async def handle_list_deck(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> str:
    return await handle_list_deck_command(args.extract_plain_text())
