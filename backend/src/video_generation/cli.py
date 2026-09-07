import argparse
import asyncio
import json
import logging

import uvicorn

from video_generation.config import Settings
from video_generation.domain.auth import initialize_owner
from video_generation.runtime import loop_factory
from video_generation.storage.database import create_database


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


def main():
    parser = argparse.ArgumentParser(description="Video Generation local management")
    sub = parser.add_subparsers(dest="command", required=True)
    owner = sub.add_parser(
        "init-owner", help="Initialize local owner and issue a one-time pairing code"
    )
    owner.add_argument("--name", default="本机创作者")
    owner.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "init-owner":
        asyncio.run(_pair(args.name, args.json), loop_factory=loop_factory)
