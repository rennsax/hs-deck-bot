"""Search registered Hearthstone decks by name."""

from nonebot import on_command
from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_search_deck_command
from hs_deck_bot.conversation_logging import public_command


search_deck = on_command(
    "search-deck",
    aliases={"找卡组"},
    priority=10,
    block=True,
)


@search_deck.handle()
@public_command(search_deck)
async def handle_search_deck(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> str:
    return await handle_search_deck_command(args.extract_plain_text())
