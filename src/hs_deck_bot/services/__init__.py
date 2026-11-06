"""Business services used by NoneBot plugins."""

from .decks import (
    DeletedDeck,
    DeckNameConflictError,
    DeckNotFoundError,
    DeckSearchResult,
    DeckStorageError,
    InvalidDeckNameError,
    RegisteredDeck,
    delete_deck,
    register_deck,
    search_decks,
)

__all__ = [
    "DeletedDeck",
    "DeckNameConflictError",
    "DeckNotFoundError",
    "DeckSearchResult",
    "DeckStorageError",
    "InvalidDeckNameError",
    "RegisteredDeck",
    "delete_deck",
    "register_deck",
    "search_decks",
]
