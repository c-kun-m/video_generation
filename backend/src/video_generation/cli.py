import argparse
import asyncio
import json
import logging

import uvicorn

from video_generation.application.auth import initialize_owner
from video_generation.config import Settings
from video_generation.infrastructure.persistence.database import create_database
from video_generation.runtime import loop_factory


def serve():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    uvicorn.run(
        "video_generation.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        loop="video_generation.runtime:loop_factory",
    )


async def _pair(name: str, as_json: bool):
    settings = Settings()
    engine, sessions = create_database(settings)
    try:
        code = await initialize_owner(sessions, settings, name)
        if as_json:
            print(json.dumps({"pairing_code": code, "expires_in": settings.pairing_ttl_seconds}))
        else:
            print(f"一次性配对码（{settings.pairing_ttl_seconds // 60} 分钟有效）：\n{code}")
            print("在桌面应用的配对页面输入此码。此码仅显示于本次管理命令。")
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Video Generation API and local management")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Start enabled project services from YAML")
    start.add_argument(
        "--config", default="startup.yml", help="Config path relative to repository root"
    )
    start.add_argument(
        "--check", action="store_true", help="Validate configuration without starting processes"
    )
    sub.add_parser("serve", help="Start the local API with the supported event loop")
    sub.add_parser("init-temporal", help="Create the local durable Temporal namespace")
    sub.add_parser("worker", help="Run the durable simulation Temporal Worker")
    sub.add_parser("dispatcher", help="Deliver and reconcile PostgreSQL outbox events")
    owner = sub.add_parser(
        "init-owner", help="Initialize local owner and issue a one-time pairing code"
    )
    owner.add_argument("--name", default="本机创作者")
    owner.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "start":
        from video_generation.launcher import launch

        raise SystemExit(launch(args.config, args.check))
    elif args.command == "serve":
        serve()
    elif args.command == "init-temporal":
        from video_generation.workers.setup import initialize_temporal

        asyncio.run(initialize_temporal(), loop_factory=loop_factory)
    elif args.command in {"worker", "dispatcher"}:
        from video_generation.workers.dispatcher import run_dispatcher
        from video_generation.workers.temporal import run_worker

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        asyncio.run(
            run_worker() if args.command == "worker" else run_dispatcher(),
            loop_factory=loop_factory,
        )
    elif args.command == "init-owner":
        asyncio.run(_pair(args.name, args.json), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
