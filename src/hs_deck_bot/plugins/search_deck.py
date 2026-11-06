"""Search registered Hearthstone decks by name."""

from nonebot import on_command
from nonebot.adapters.qq import Message
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_search_deck_command


search_deck = on_command(
    "search-deck",
    aliases={"找卡组"},
    priority=10,
    block=True,
)


@search_deck.handle()
async def handle_search_deck(args: Message = CommandArg()) -> None:
    await search_deck.finish(
        await handle_search_deck_command(args.extract_plain_text())
    )
