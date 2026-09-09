import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from video_generation import launcher
from video_generation.config import REPO_ROOT
from video_generation.infrastructure.processes import OwnedProcess
from video_generation.launcher import LaunchConfig, LaunchError, Supervisor


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for child process")


def config(services, prepare=None):
    return LaunchConfig.model_validate(
        {"version": 1, "services": services, "prepare": prepare or {}}
    )


def command(code):
    return [sys.executable, "-c", code]


def supervisor(tmp_path, configuration):
    return Supervisor(
        configuration, {"python": sys.executable, "api_url": "http://127.0.0.1:18004"}, tmp_path
    )


@pytest.mark.parametrize(
    "content",
    [
        "version: 1\nservices:\n  worker: {enabled: false, command: [python]}\n",
        "version: 1\nservices:\n  worker: {enabled: true, command: [python], typo: true}\n",
        'version: 1\nservices:\n  worker: {enabled: "false", command: [python]}\n',
        "version: 1\nservices:\n  worker: {command: [python]}\n  worker: {command: [python]}\n",
        "!!python/object/apply:os.system [echo unexpected]\n",
    ],
)
def test_invalid_yaml_never_starts_processes(tmp_path, monkeypatch, content):
    path = tmp_path / "invalid.yml"
    path.write_text(content, encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid configuration spawned a process")

    monkeypatch.setattr(launcher, "OwnedProcess", forbidden)
    assert launcher.launch(str(path)) == 1


@pytest.mark.parametrize("directory", [REPO_ROOT, REPO_ROOT / "backend"])
def test_check_config_resolves_root_without_launching(directory):
    result = subprocess.run(
        [sys.executable, "-m", "video_generation", "start", "--check"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "services.worker: enabled" in result.stdout
    assert "no commands executed" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="PowerShell launcher")
def test_powershell_start_from_activated_venv_does_not_require_uv_in_venv():
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run(
        [
            shutil.which("powershell"),
            "-NoProfile",
            "-File",
            str(REPO_ROOT / "scripts/dev.ps1"),
            "start",
            "-Check",
        ],
        cwd=REPO_ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "no commands executed" in result.stdout


def test_disabled_service_is_not_started(tmp_path):
    marker = tmp_path / "disabled.txt"
    enabled_marker = tmp_path / "enabled.txt"
    settings = config(
        {
            "disabled": {
                "enabled": False,
                "command": command(f"from pathlib import Path; Path({str(marker)!r}).touch()"),
            },
            "enabled": {
                "command": command(
                    f"import time; from pathlib import Path; Path({str(enabled_marker)!r}).touch(); time.sleep(1)"
                ),
                "stop_project_on_exit": False,
            },
        }
    )
    supervisor(tmp_path, settings).run()
    assert enabled_marker.exists() and not marker.exists()


def test_preparation_failure_prevents_all_services(tmp_path):
    marker = tmp_path / "service.txt"
    settings = config(
        {"api": {"command": command(f"from pathlib import Path; Path({str(marker)!r}).touch()")}},
        {"migration": {"command": command("raise SystemExit(7)")}},
    )
    with pytest.raises(LaunchError, match="Preparation migration failed"):
        supervisor(tmp_path, settings).run()
    assert not marker.exists()


def test_occupied_port_is_not_adopted_or_stopped(tmp_path):
    marker = tmp_path / "service.txt"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        settings = config(
            {
                "api": {
                    "command": command(f"from pathlib import Path; Path({str(marker)!r}).touch()"),
                    "ready_url": f"http://127.0.0.1:{port}/health/ready",
                }
            }
        )
        with pytest.raises(LaunchError, match="occupied"):
            supervisor(tmp_path, settings).run()
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    assert not marker.exists()


def test_optional_desktop_exit_does_not_stop_backend(tmp_path):
    marker = tmp_path / "backend-still-running.txt"
    settings = config(
        {
            "api": {
                "command": command(
                    f"import time; from pathlib import Path; time.sleep(1.8); Path({str(marker)!r}).touch(); time.sleep(0.5)"
                )
            },
            "desktop": {
                "command": command("import time; time.sleep(0.8)"),
                "stop_project_on_exit": False,
            },
        }
    )
    with pytest.raises(LaunchError, match="api exited"):
        supervisor(tmp_path, settings).run()
    assert marker.exists()


def test_required_service_failure_and_readiness_timeout_close_owned_trees(tmp_path):
    settings = config(
        {
            "api": {"command": command("import time; time.sleep(0.9); raise SystemExit(5)")},
            "worker": {"command": command("import time; time.sleep(60)")},
        }
    )
    running = supervisor(tmp_path, settings)
    children = []
    spawn = running.spawn

    def capture(name, spec):
        child = spawn(name, spec)
        children.append(child)
        return child

    running.spawn = capture
    with pytest.raises(LaunchError, match="api exited"):
        running.run()
    assert children and all(child.poll() is not None for child in children)
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    settings = config(
        {
            "unready": {
                "command": command("import time; time.sleep(60)"),
                "ready_url": f"http://127.0.0.1:{port}/",
                "timeout_seconds": 1,
            }
        }
    )
    with pytest.raises(LaunchError, match="readiness timed out"):
        supervisor(tmp_path, settings).run()


def test_launcher_lock_rejects_duplicate_and_releases_after_exit():
    with launcher.project_lock():
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "from video_generation.launcher import project_lock; exec('with project_lock():\\n print(\"unexpected\")')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert child.returncode != 0 and "already has a running launcher" in child.stderr
    with launcher.project_lock():
        pass


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ownership")
def test_owned_tree_is_killed_on_close_even_when_parent_was_killed(tmp_path):
    marker = tmp_path / "descendant.txt"
    code = f"import os,time; from pathlib import Path; Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    own = OwnedProcess(command(code), REPO_ROOT, tmp_path / "owned.log", dict(os.environ))
    # An unrelated process must survive closing the owned tree.
    unrelated = subprocess.Popen(
        [getattr(sys, "_base_executable", sys.executable), "-c", "import time; time.sleep(60)"]
    )
    try:
        pid = int(wait_for(lambda: marker.read_text() if marker.exists() else None))
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        assert handle
        try:
            own.process.kill()
            own.process.wait(timeout=5)
            own.close()
            assert kernel.WaitForSingleObject(handle, 5000) == 0
            assert unrelated.poll() is None
        finally:
            kernel.CloseHandle(handle)
    finally:
        own.close()
        unrelated.kill()
        unrelated.wait(timeout=5)
