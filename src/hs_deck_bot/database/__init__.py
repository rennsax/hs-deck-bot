"""Database access for persisted Hearthstone decks."""

from .catalog import (
    CardCatalogError,
    CardCatalogRegressionError,
    CardCatalogUnavailableError,
    clear_card_index,
    get_card_index,
    initialize_card_catalog,
    sync_card_catalog,
)
from .models import (
    Base,
    CardCatalogStateModel,
    CardModel,
    DeckCardModel,
    DeckModel,
)
from .session import (
    DatabaseConfigError,
    DatabaseError,
    configure_database,
    dispose_database,
    session_scope,
)

__all__ = [
    "Base",
    "CardCatalogError",
    "CardCatalogRegressionError",
    "CardCatalogStateModel",
    "CardCatalogUnavailableError",
    "CardModel",
    "DatabaseConfigError",
    "DatabaseError",
    "DeckCardModel",
    "DeckModel",
    "clear_card_index",
    "configure_database",
    "dispose_database",
    "get_card_index",
    "initialize_card_catalog",
    "session_scope",
    "sync_card_catalog",
]
