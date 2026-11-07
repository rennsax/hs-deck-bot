"""Query localized Hearthstone deck lists."""

from nonebot import on_command
from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_deck_command
from hs_deck_bot.conversation_logging import public_command


deck = on_command(
    "deck",
    aliases={"卡组"},
    priority=10,
    block=True,
)


@deck.handle()
@public_command(deck)
async def handle_deck(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> str:
    return await handle_deck_command(args.extract_plain_text())
