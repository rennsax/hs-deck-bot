"""Initialize shared application resources for NoneBot plugins."""

from nonebot import get_driver, logger

from hs_deck_bot.database import (
    clear_card_index,
    dispose_database,
    initialize_card_catalog,
)


driver = get_driver()


@driver.on_startup
async def initialize_resources() -> None:
    logger.info("正在初始化炉石卡牌目录")
    await initialize_card_catalog()
    logger.info("炉石卡牌目录初始化完成")


@driver.on_shutdown
async def dispose_resources() -> None:
    clear_card_index()
    await dispose_database()
