"""Alembic environment. The database URL comes from application settings."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from backend.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

# Better Auth creates and owns these tables through its own migrator.
# Alembic autogenerate must leave them alone.
BETTER_AUTH_TABLES = frozenset({"user", "session", "account", "verification"})


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    del parent_names
    return not (type_ == "table" and name in BETTER_AUTH_TABLES)


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_settings().database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
