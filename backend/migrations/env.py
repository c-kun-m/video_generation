import asyncio

from alembic import context

from video_generation.config import Settings
from video_generation.runtime import loop_factory
from video_generation.storage.database import create_database
from video_generation.storage.models import Base


def run_sync(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine, _ = create_database(Settings())
    async with engine.connect() as connection:
        await connection.run_sync(run_sync)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online(), loop_factory=loop_factory)
