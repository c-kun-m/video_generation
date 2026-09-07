import asyncio
import sys


def loop_factory() -> asyncio.AbstractEventLoop:
    # Psycopg's async connections require a selector loop on Windows.
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
