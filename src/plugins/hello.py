from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
hello = on_command("hello")
@hello.handle()
async def _(event: MessageEvent):
    await hello.finish("Hello, QQ!")
