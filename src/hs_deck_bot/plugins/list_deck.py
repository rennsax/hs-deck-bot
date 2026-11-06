"""List registered public Hearthstone decks."""

from nonebot import on_command
from nonebot.adapters.qq import Message
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_list_deck_command


list_deck = on_command(
    "list-deck",
    aliases={"所有卡组"},
    priority=10,
    block=True,
)


@list_deck.handle()
async def handle_list_deck(args: Message = CommandArg()) -> None:
    await list_deck.finish(
        await handle_list_deck_command(args.extract_plain_text())
    )
