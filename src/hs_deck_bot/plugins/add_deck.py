"""Register public Hearthstone decks."""

from nonebot import on_command
from nonebot.adapters.qq import GroupMessageCreateEvent, Message, MessageEvent
from nonebot.params import CommandArg

from hs_deck_bot.commands import handle_add_deck_command


add_deck = on_command("add-deck", priority=10, block=True)


@add_deck.handle()
async def handle_add_deck(
    event: MessageEvent,
    args: Message = CommandArg(),
) -> None:
    await add_deck.finish(
        await handle_add_deck_command(args.extract_plain_text())
    )
