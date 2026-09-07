"""Create a dedicated test database; never reset or delete an existing database."""

import os
import subprocess

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from video_generation.config import REPO_ROOT, Settings


def main():
    production = make_url(Settings().database_url.get_secret_value())
    test = make_url(
        os.getenv(
            "VIDEO_TEST_DATABASE_URL",
            production.set(database="video_generation_test").render_as_string(
                hide_password=False
            ),
        )
    )
    if (
        not test.database
        or not test.database.endswith("_test")
        or test.database == production.database
    ):
        raise SystemExit(
            "Test database must end with _test and differ from the application database"
        )
    maintenance = test.set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        maintenance.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        if not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (test.database,)
        ).fetchone():
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test.database))
            )
    env = {
        **os.environ,
        "VIDEO_DATABASE_URL": test.render_as_string(hide_password=False),
    }
    subprocess.run(
        [
            str(REPO_ROOT / "backend/.venv/Scripts/alembic.exe")
            if os.name == "nt"
            else str(REPO_ROOT / "backend/.venv/bin/alembic"),
            "-c",
            str(REPO_ROOT / "backend/alembic.ini"),
            "upgrade",
            "head",
        ],
        env=env,
        check=True,
    )
    print("Dedicated test database is ready.")


if __name__ == "__main__":
    main()
