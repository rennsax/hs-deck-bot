"""Delete registered public Hearthstone decks."""

from nonebot import on_command
from nonebot.adapters.qq import Message
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_delete_deck_command


delete_deck = on_command(
    "delete-deck",
    aliases={"删卡组"},
    priority=10,
    block=True,
)


@delete_deck.handle()
async def handle_delete_deck(args: Message = CommandArg()) -> None:
    await delete_deck.finish(
        await handle_delete_deck_command(args.extract_plain_text())
    )
