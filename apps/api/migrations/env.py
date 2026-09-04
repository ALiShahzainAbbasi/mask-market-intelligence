import mask_api.persistence.registry  # noqa: F401
from alembic import context
from mask_api.config import get_settings
from mask_api.database import create_db_engine
from mask_api.persistence.base import Base

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url="postgresql+psycopg://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_db_engine(get_settings(), migration=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
