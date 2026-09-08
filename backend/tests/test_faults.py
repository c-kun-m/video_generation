import pytest
from pydantic import ValidationError

from video_generation.config import Settings
from video_generation.workers.faults import crash_if_selected


def test_fault_injection_requires_dedicated_database():
    with pytest.raises(ValidationError, match="dedicated _test database"):
        Settings(
            _env_file=None, database_url="postgresql://video@localhost/video", test_faults=True
        )


def test_fault_gate_is_disabled_by_default_and_requires_exact_operation(monkeypatch):
    exits = []
    monkeypatch.setattr("video_generation.workers.faults.os._exit", exits.append)
    monkeypatch.setenv("VIDEO_TEST_CRASH_POINT", "api_after_commit")
    monkeypatch.setenv("VIDEO_TEST_CRASH_ID", "selected-command")
    settings = Settings(_env_file=None, database_url="postgresql://video@localhost/fault_test")
    assert settings.test_faults is False
    crash_if_selected(settings, "api_after_commit", "selected-command")
    assert exits == []
    settings = Settings(
        _env_file=None, database_url="postgresql://video@localhost/fault_test", test_faults=True
    )
    crash_if_selected(settings, "activity_after_commit", "selected-command")
    crash_if_selected(settings, "api_after_commit", "another-command")
    assert exits == []
    crash_if_selected(settings, "api_after_commit", "selected-command")
    assert exits == [91]
