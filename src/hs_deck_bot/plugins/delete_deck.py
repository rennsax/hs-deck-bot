"""Delete registered public Hearthstone decks."""

from nonebot import on_command
from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_delete_deck_command
from hs_deck_bot.conversation_logging import public_command


delete_deck = on_command(
    "delete-deck",
    aliases={"删卡组"},
    priority=10,
    block=True,
)


@delete_deck.handle()
@public_command(delete_deck)
async def handle_delete_deck(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> str:
    return await handle_delete_deck_command(args.extract_plain_text())
