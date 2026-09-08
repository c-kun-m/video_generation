"""Explicit process-death gates for dedicated test databases only; disabled by default."""

import os

from video_generation.config import Settings


def crash_if_selected(settings: Settings, point: str, identity: str):
    if not settings.test_faults:
        return
    # A configured marker selects one exact operation; ordinary traffic cannot trigger this.
    if (
        os.getenv("VIDEO_TEST_CRASH_POINT") == point
        and os.getenv("VIDEO_TEST_CRASH_ID") == identity
    ):
        os._exit(91)
