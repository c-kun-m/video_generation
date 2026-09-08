import os

import httpx
import pytest
from sqlalchemy.engine import make_url

from video_generation.api.app import create_app
from video_generation.application.auth import initialize_owner
from video_generation.config import Settings
from video_generation.runtime import loop_factory


def pytest_asyncio_loop_factories(config, item):
    return {"application": loop_factory}


@pytest.fixture
async def app():
    url = make_url(Settings().database_url.get_secret_value())
    test_url = make_url(
        os.getenv(
            "VIDEO_TEST_DATABASE_URL",
            url.set(database="video_generation_test").render_as_string(hide_password=False),
        )
    )
    assert test_url.database.endswith("_test") and test_url.database != url.database
    settings = Settings(database_url=test_url.render_as_string(hide_password=False))
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        code = await initialize_owner(app.state.sessions, app.state.settings)
        response = await client.post(
            "/video/v1/auth/pair", json={"pairing_code": code, "device_name": "pytest"}
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        yield client
