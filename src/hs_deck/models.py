"""Public card and deck models."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from manacost_deckstrings import DeckstringError, decode

from .cache import CardMetadata
from .errors import CardNotFoundError, DeckCodeError


CLASS_NAMES = {
    "DEATHKNIGHT": "死亡骑士",
    "DEMONHUNTER": "恶魔猎手",
    "DRUID": "德鲁伊",
    "HUNTER": "猎人",
    "MAGE": "法师",
    "PALADIN": "圣骑士",
    "PRIEST": "牧师",
    "ROGUE": "潜行者",
    "SHAMAN": "萨满祭司",
    "WARLOCK": "术士",
    "WARRIOR": "战士",
}

FORMAT_NAMES = {
    1: "狂野模式",
    2: "标准模式",
    3: "经典模式",
    4: "幻变模式",
}


@dataclass(frozen=True, slots=True)
class Card:
    """A localized Hearthstone card appearing in a deck."""

    dbf_id: int
    card_id: str
    name: str
    cost: int | None
    card_type: str | None = None
    card_class: str | None = None
    collectible: bool | None = None
    sideboard_owner_dbf_id: int | None = None
    sideboard_owner_name: str | None = None
    _metadata: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "_metadata", _freeze_mapping(self._metadata))

    @classmethod
    def _from_metadata(
        cls,
        metadata: CardMetadata,
        *,
        sideboard_owner_dbf_id: int | None = None,
        sideboard_owner_name: str | None = None,
    ) -> "Card":
        cost = metadata.get("cost")
        card_type = metadata.get("type")
        card_class = metadata.get("cardClass")
        collectible = metadata.get("collectible")
        return cls(
            dbf_id=metadata["dbfId"],
            card_id=str(metadata.get("id", "")),
            name=str(metadata.get("name") or metadata["dbfId"]),
            cost=cost if isinstance(cost, int) else None,
            card_type=card_type if isinstance(card_type, str) else None,
            card_class=card_class if isinstance(card_class, str) else None,
            collectible=collectible if isinstance(collectible, bool) else None,
            sideboard_owner_dbf_id=sideboard_owner_dbf_id,
            sideboard_owner_name=sideboard_owner_name,
            _metadata=_freeze_mapping(metadata),
        )

    @property
    def class_name(self) -> str | None:
        """Return the localized class name when the card has a class."""

        if self.card_class is None:
            return None
        return CLASS_NAMES.get(self.card_class, self.card_class)

    @property
    def is_sideboard(self) -> bool:
        """Whether this card is attached to another card's sideboard."""

        return self.sideboard_owner_dbf_id is not None

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Return the original localized metadata as a read-only mapping."""

        return self._metadata

    @property
    def basic_info(self) -> dict[str, object]:
        """Return basic card information suitable for plugin responses."""

        return {
            "dbf_id": self.dbf_id,
            "card_id": self.card_id,
            "name": self.name,
            "cost": self.cost,
            "type": self.card_type,
            "class": self.class_name,
            "collectible": self.collectible,
            "is_sideboard": self.is_sideboard,
            "sideboard_owner_dbf_id": self.sideboard_owner_dbf_id,
            "sideboard_owner_name": self.sideboard_owner_name,
        }

    def __str__(self) -> str:
        cost = self.cost if self.cost is not None else 0
        result = f"({cost}) {self.name}"
        if self.is_sideboard:
            owner = self.sideboard_owner_name or str(self.sideboard_owner_dbf_id)
            result += f" [备选牌：{owner}]"
        return result


@dataclass(frozen=True, slots=True)
class Deck:
    """A decoded and localized Hearthstone deck."""

    name: str
    deck_code: str
    hero: Card
    cards: tuple[Card, ...]
    sideboard_cards: tuple[Card, ...]
    class_name: str
    format_id: int
    format_name: str

    @classmethod
    def from_code(
        cls,
        deck_code: str,
        deck_name: str = "卡组名",
        *,
        card_index: Mapping[int, CardMetadata],
    ) -> "Deck":
        """Build a localized deck from a Hearthstone deck code and name."""

        normalized_code = deck_code.strip()
        try:
            decoded = decode(normalized_code)
        except DeckstringError as error:
            raise DeckCodeError(
                f"无法解析卡组代码：{error}",
                code=str(error.code),
            ) from error

        if len(decoded["heroes"]) != 1:
            raise DeckCodeError("卡组代码必须包含且仅包含一个英雄")

        hero = Card._from_metadata(
            _require_metadata(card_index, decoded["heroes"][0])
        )

        main_cards = []
        for dbf_id, count in decoded["cards"]:
            card = Card._from_metadata(
                _require_metadata(card_index, dbf_id),
            )
            main_cards.extend([card] * count)
        main_cards = _sort_expanded_main_cards(tuple(main_cards))

        sideboard_cards = []
        for dbf_id, count, owner_dbf_id in decoded["sideboardCards"]:
            owner_metadata = card_index.get(owner_dbf_id)
            owner_name = (
                str(owner_metadata.get("name") or owner_dbf_id)
                if owner_metadata is not None
                else None
            )
            card = Card._from_metadata(
                _require_metadata(card_index, dbf_id),
                sideboard_owner_dbf_id=owner_dbf_id,
                sideboard_owner_name=owner_name,
            )
            sideboard_cards.extend([card] * count)

        sideboard_cards.sort(
            key=lambda card: (
                card.sideboard_owner_dbf_id or 0,
                card.cost or 0,
                card.name,
            )
        )

        format_id = decoded["format"]
        card_class = hero.card_class or "UNKNOWN"
        normalized_name = " ".join(deck_name.split()) or "卡组名"
        return cls(
            name=normalized_name,
            deck_code=normalized_code,
            hero=hero,
            cards=main_cards,
            sideboard_cards=tuple(sideboard_cards),
            class_name=CLASS_NAMES.get(card_class, card_class),
            format_id=format_id,
            format_name=FORMAT_NAMES.get(format_id, str(format_id)),
        )

    @property
    def card_count(self) -> int:
        """Return the number of cards in the main deck."""

        return len(self.cards)

    @property
    def basic_info(self) -> dict[str, object]:
        """Return basic deck information suitable for plugin responses."""

        return {
            "name": self.name,
            "class": self.class_name,
            "format_id": self.format_id,
            "format": self.format_name,
            "hero": self.hero.name,
            "card_count": self.card_count,
            "sideboard_card_count": len(self.sideboard_cards),
        }

    def __str__(self) -> str:
        lines = [
            f"### {self.name}",
            f"# 职业：{self.class_name}",
            f"# 模式：{self.format_name}",
            "#",
        ]
        lines.extend(_format_card_lines(self.cards, sideboard=False))
        lines.extend(_format_card_lines(self.sideboard_cards, sideboard=True))
        lines.extend(
            [
                "#",
                self.deck_code,
                "#",
                "# 想要使用这副套牌，请先复制到剪贴板，"
                "然后在游戏中点击“新套牌”进行粘贴。",
            ]
        )
        return "\n".join(lines)


def _require_metadata(
    card_index: Mapping[int, CardMetadata],
    dbf_id: int,
) -> CardMetadata:
    try:
        return card_index[dbf_id]
    except KeyError as error:
        raise CardNotFoundError(dbf_id) from error


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {key: _freeze_value(item) for key, item in value.items()}
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _sort_unique_main_cards(cards: tuple[Card, ...]) -> tuple[Card, ...]:
    children: dict[int, list[Card]] = defaultdict(list)
    grouped_children: set[int] = set()

    for child in cards:
        if child.collectible is True:
            continue

        parents = [
            parent
            for parent in cards
            if parent.collectible is True
            and child.card_id != parent.card_id
            and child.card_id.startswith(parent.card_id)
        ]
        if parents:
            parent = max(parents, key=lambda card: len(card.card_id))
            children[parent.dbf_id].append(child)
            grouped_children.add(child.dbf_id)

    roots = sorted(
        (card for card in cards if card.dbf_id not in grouped_children),
        key=lambda card: (card.cost or 0, card.name),
    )

    result: list[Card] = []
    for root in roots:
        result.append(root)
        result.extend(
            sorted(children.get(root.dbf_id, []), key=lambda card: card.dbf_id)
        )
    return tuple(result)


def _sort_expanded_main_cards(cards: tuple[Card, ...]) -> tuple[Card, ...]:
    counts = Counter(cards)
    ordered_cards = _sort_unique_main_cards(tuple(counts))
    return tuple(
        card
        for card in ordered_cards
        for _ in range(counts[card])
    )


def _format_card_lines(
    cards: tuple[Card, ...],
    *,
    sideboard: bool,
) -> list[str]:
    counts = Counter(cards)
    if sideboard:
        ordered_cards = sorted(
            counts,
            key=lambda card: (
                card.sideboard_owner_dbf_id or 0,
                card.cost or 0,
                card.name,
            ),
        )
    else:
        ordered_cards = _sort_unique_main_cards(tuple(counts))
    return [f"# {counts[card]}x {card}" for card in ordered_cards]
