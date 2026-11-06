"""Query localized Hearthstone deck lists."""

from nonebot import on_command
from nonebot.adapters.qq import Message
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_deck_command


deck = on_command("deck", priority=10, block=True)


@deck.handle()
async def handle_deck(args: Message = CommandArg()) -> None:
    await deck.finish(
        await handle_deck_command(args.extract_plain_text())
    )
