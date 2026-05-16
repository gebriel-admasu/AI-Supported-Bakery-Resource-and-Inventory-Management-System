"""Alembic environment for the AI forecasting service.

This Alembic config only manages the four AI-owned tables (ai_model_registry,
ai_forecasts, ai_forecast_actuals, ai_mlops_logs). It deliberately points at
the same SQLite file the backend uses so both services share one database.

Because the AI tables are prefixed with ``ai_`` and we register our own
``Base.metadata`` here (not the backend's), autogenerate will never propose
changes to backend-owned tables.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.config import settings
from app.database import Base

import app.db.models  # noqa: F401 — registers all AI models with Base.metadata


config = context.config
config.set_main_option("sqlalchemy.url", settings.resolved_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(object_, name, type_, reflected, compare_to):  # noqa: ANN001
    """Tell Alembic to ignore tables it didn't create.

    Without this, autogenerate would see the backend's tables (users, stores,
    sales_records, …) in the shared database and propose to drop them. This
    filter scopes autogenerate strictly to tables whose name starts with
    ``ai_`` — which is the prefix we use for everything the AI service owns.
    """
    if type_ == "table" and not name.startswith("ai_"):
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
