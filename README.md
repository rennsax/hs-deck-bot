# hs-deck-bot

NoneBot 炉石卡组查询与公共卡组存储服务。

## 数据库准备

在 `.env` 中配置 `HS_DECK_DATABASE_URL`，例如开发数据库：

```text
sqlite+aiosqlite:///./decks-dev.sqlite3
```

首次使用前执行 migration：

```bash
uv run alembic upgrade head
```

Bot 或命令行程序启动时会初始化完整中文卡牌目录。数据库没有可用目录时会访问 HearthstoneJSON 下载数据。

## 配置 Bot

在 `.env` 中配置 `QQ_BOTS`：

``` text
QQ_BOTS='[
  {
    "id": "<AppID>",
    "secret": "<AppSecret>",
    "intent": {
      "c2c_group_at_messages": true
    }
  }
]'
```

`c2c_group_at_messages` 表示要么私聊机器人，要么在群里 @ 机器人。

## 启动 Bot

```bash
nb run
```

## 命令行前端

包 `hs_deck_bot` 提供命令行前端用于测试、管理数据库，可以交互式直接运行：

```bash
uv run python -m hs_deck_bot
# or
uv run hs-deck-bot
```

Bot 与命令行前端共同公开的命令共用业务逻辑，因此参数校验、数据库操作和回复文本保持一致；命令行前端也可以提供仅供测试或管理使用的独有命令。

## hs_deck_bot 插件接口

### `/deck <卡组代码>`

解析炉石 Deckstring，并返回完整的中文卡表。输出包括职业、模式、主牌、备选牌、原始卡组代码以及炉石客户端的导入提示。

参数：

- `卡组代码`：完整的原始 Deckstring，不接受炉石剪贴板中的其他说明文本。

示例：

```text
/deck AAEBA...
```

常见错误：卡组代码无效、卡牌目录缺少对应卡牌或卡牌目录暂时不可用。

### `/add-deck <卡组名> <创建者> <卡组代码>`

解析卡组并将其注册为公共卡组，创建者是用户填写的文本标签，不绑定真实 QQ 用户。

参数：

- `卡组名`：**不含空格**，不能为空，最长 255 个字符。
- `创建者`：**不含空格**，不能为空，最长 255 个字符。
- `卡组代码`：完整的原始 Deckstring。

命令严格按空白分割参数。示例：

```text
/add-deck 奇迹贼 玩家A AAEBA...
```

注册成功后返回卡组名、创建者、职业、模式和主牌数量。卡组内容写入 `decks` 和 `deck_cards`，涉及的英雄、主牌和备选牌必须已经存在于卡牌目录中。

同一创建者不能重复注册同名卡组；不同创建者可以使用相同卡组名。

常见错误：卡组代码无效、卡牌目录尚未更新、名称冲突或数据库暂时不可用、同一创建者注册同名卡组。
