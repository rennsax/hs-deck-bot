"""Small command-line smoke test for :mod:`hs_deck`."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import Deck, HsDeckError


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将炉石卡组代码转换为中文卡表")
    parser.add_argument("deck_code", help="炉石卡组代码")
    parser.add_argument("--name", default="卡组名", help="卡组名称")
    parser.add_argument("--cache-dir", type=Path, help="覆盖默认缓存目录")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="强制刷新简体中文卡牌数据",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        deck = Deck.from_code(
            args.deck_code,
            args.name,
            cache_dir=args.cache_dir,
            force_refresh=args.force_refresh,
        )
    except HsDeckError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    print(deck)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
