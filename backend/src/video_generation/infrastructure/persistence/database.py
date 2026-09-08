from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from video_generation.config import Settings


def create_database(settings: Settings):
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args={"connect_timeout": 3},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)
