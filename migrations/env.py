import asyncio
from logging.config import fileConfig
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from hs_deck_bot.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Load the database URL from the project dotenv configuration."""

    project_root = Path(__file__).resolve().parents[1]
    base_env_file = project_root / ".env"
    base_config = dotenv_values(base_env_file)
    environment = (
        os.getenv("ENVIRONMENT")
        or base_config.get("ENVIRONMENT")
        or "prod"
    )
    environment_config = dotenv_values(
        project_root / f".env.{environment}"
    )
    database_url = (
        os.getenv("HS_DECK_DATABASE_URL")
        or environment_config.get("HS_DECK_DATABASE_URL")
        or base_config.get("HS_DECK_DATABASE_URL")
    )
    if not database_url:
        raise RuntimeError(
            "HS_DECK_DATABASE_URL 未设置；请通过环境变量、.env 或当前"
            "环境对应的 .env.{ENVIRONMENT} 提供。"
        )
    return str(database_url)


# ConfigParser treats percent signs as interpolation markers. Escaping them
# keeps percent-encoded database URLs intact.
config.set_main_option("sqlalchemy.url", get_database_url().replace("%", "%%"))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
