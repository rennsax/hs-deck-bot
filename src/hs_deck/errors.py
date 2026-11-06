"""Public exceptions raised by :mod:`hs_deck`."""

from __future__ import annotations


class HsDeckError(Exception):
    """Base class for errors raised by this package."""


class DeckCodeError(HsDeckError):
    """Raised when a Hearthstone deck code cannot be decoded."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class CardIndexError(HsDeckError):
    """Raised when no usable card index can be loaded."""


class CardNotFoundError(HsDeckError):
    """Raised when a DBF ID is missing from the localized card index."""

    def __init__(self, dbf_id: int) -> None:
        super().__init__(f"卡牌索引中不存在 DBF ID {dbf_id}")
        self.dbf_id = dbf_id
