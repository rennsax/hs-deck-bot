"""Localized Hearthstone card-index caching."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any

import httpx
from platformdirs import user_cache_path

from .errors import CardIndexError


CARD_DATA_URL = "https://api.hearthstonejson.com/v1/latest/zhCN/cards.json"
CARD_CATALOG_SCHEMA_VERSION = 1
CACHE_FILE_NAME = "cards-zhCN.json"
DEFAULT_CACHE_TTL = timedelta(days=7)
DOWNLOAD_TIMEOUT = 30.0

CardMetadata = Mapping[str, Any]
CardIndex = dict[int, CardMetadata]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _MemoryEntry:
    fetched_at: datetime
    index: CardIndex


@dataclass(frozen=True, slots=True)
class CardCatalogSnapshot:
    """A validated card catalog fetched without persistent caching."""

    schema_version: int
    fetched_at: datetime
    source_url: str
    cards: tuple[CardMetadata, ...]
    index: CardIndex


_memory_cache: dict[Path, _MemoryEntry] = {}
_cache_lock = RLock()


def _cache_file(cache_dir: str | Path | None) -> Path:
    directory = (
        Path(cache_dir).expanduser()
        if cache_dir is not None
        else user_cache_path("hs-deck-bot")
    )
    return directory / CACHE_FILE_NAME


def _parse_fetched_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("缓存缺少 fetched_at")

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("缓存时间必须包含时区")
    return parsed.astimezone(timezone.utc)


def _build_index(cards: object) -> tuple[list[CardMetadata], CardIndex]:
    if not isinstance(cards, list) or not cards:
        raise ValueError("卡牌缓存不是非空列表")

    normalized: list[CardMetadata] = []
    index: CardIndex = {}
    card_ids: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("卡牌缓存包含非对象条目")

        dbf_id = card.get("dbfId")
        if not isinstance(dbf_id, int) or isinstance(dbf_id, bool):
            raise ValueError("卡牌缓存条目缺少整数 dbfId")
        if dbf_id in index:
            raise ValueError(f"卡牌缓存包含重复 dbfId：{dbf_id}")

        card_id = card.get("id")
        if not isinstance(card_id, str) or not card_id:
            raise ValueError(f"卡牌缓存条目 {dbf_id} 缺少 id")
        if card_id in card_ids:
            raise ValueError(f"卡牌缓存包含重复 id：{card_id}")

        name = card.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"卡牌缓存条目 {dbf_id} 缺少中文名称")

        normalized.append(card)
        index[dbf_id] = card
        card_ids.add(card_id)

    return normalized, index


def _read_cache(path: Path) -> _MemoryEntry:
    with path.open("r", encoding="utf-8") as cache_file:
        payload = json.load(cache_file)

    if not isinstance(payload, dict):
        raise ValueError("缓存根节点不是对象")
    if payload.get("schema_version") != CARD_CATALOG_SCHEMA_VERSION:
        raise ValueError("缓存 schema 版本不兼容")

    fetched_at = _parse_fetched_at(payload.get("fetched_at"))
    _, index = _build_index(payload.get("cards"))
    return _MemoryEntry(fetched_at=fetched_at, index=index)


def fetch_card_catalog() -> CardCatalogSnapshot:
    """Download and validate the complete Simplified Chinese card catalog."""

    try:
        response = httpx.get(
            CARD_DATA_URL,
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT,
        )
        response.raise_for_status()
        cards, index = _build_index(response.json())
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
        raise CardIndexError(f"下载简体中文卡牌数据失败：{error}") from error

    return CardCatalogSnapshot(
        schema_version=CARD_CATALOG_SCHEMA_VERSION,
        fetched_at=datetime.now(timezone.utc),
        source_url=CARD_DATA_URL,
        cards=tuple(cards),
        index=index,
    )


def _write_cache(
    path: Path,
    fetched_at: datetime,
    cards: list[CardMetadata],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CARD_CATALOG_SCHEMA_VERSION,
        "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
        "source_url": CARD_DATA_URL,
        "cards": cards,
    }

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as cache_file:
            json.dump(payload, cache_file, ensure_ascii=False, separators=(",", ":"))
            cache_file.flush()
            os.fsync(cache_file.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        raise CardIndexError(f"写入卡牌缓存失败：{error}") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def load_card_index(
    *,
    cache_dir: str | Path | None = None,
    force_refresh: bool = False,
) -> CardIndex:
    """Load the localized card index, refreshing it at most once per week.

    A valid stale cache remains usable when a refresh cannot reach the remote
    data source. The returned mapping is process-local and must be treated as
    read-only by callers.
    """

    path = _cache_file(cache_dir)
    now = datetime.now(timezone.utc)

    with _cache_lock:
        stale_entry = _memory_cache.get(path)
        if stale_entry is None and path.is_file():
            try:
                stale_entry = _read_cache(path)
                _memory_cache[path] = stale_entry
            except (OSError, json.JSONDecodeError, ValueError) as error:
                logger.warning("忽略损坏的卡牌缓存 %s：%s", path, error)

        if (
            stale_entry is not None
            and not force_refresh
            and now - stale_entry.fetched_at < DEFAULT_CACHE_TTL
        ):
            return stale_entry.index

        try:
            snapshot = fetch_card_catalog()
            _write_cache(path, snapshot.fetched_at, list(snapshot.cards))
        except CardIndexError as error:
            if stale_entry is not None:
                logger.warning("卡牌数据刷新失败，继续使用旧缓存：%s", error)
                return stale_entry.index
            raise

        entry = _MemoryEntry(
            fetched_at=snapshot.fetched_at,
            index=snapshot.index,
        )
        _memory_cache[path] = entry
        return entry.index
