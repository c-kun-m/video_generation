"""Run the enabled local processes from startup.yml; API and Worker remain independent."""

import os
import re
import shutil
import signal
import socket
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from video_generation.config import REPO_ROOT, Settings
from video_generation.infrastructure.processes import OwnedProcess


class LaunchError(Exception):
    pass


class UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise LaunchError("YAML keys must be unique strings; check for duplicate entries.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


class CommandConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool = True
    command: list[str] = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: int = Field(default=30, ge=1, le=600)

    @field_validator("command")
    @classmethod
    def nonempty_command(cls, value):
        if any(not part or "\x00" in part for part in value):
            raise ValueError("command arguments must be non-empty strings without NUL")
        return value


class ServiceConfig(CommandConfig):
    ready_url: str | None = None
    stop_project_on_exit: bool = True


Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]


class LaunchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    prepare: dict[Name, CommandConfig] = Field(default_factory=dict)
    services: dict[Name, ServiceConfig] = Field(min_length=1)


def load_config(path: Path) -> LaunchConfig:
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueSafeLoader)
        config = LaunchConfig.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
            for error in exc.errors(include_input=False, include_context=False)
        )
        raise LaunchError(f"Invalid startup configuration: {details}") from None
    except (OSError, yaml.YAMLError) as exc:
        raise LaunchError(
            f"Cannot read startup configuration: {path} ({type(exc).__name__})"
        ) from None
    if not any(service.enabled for service in config.services.values()):
        raise LaunchError("Enable at least one service in startup.yml.")
    return config


def substitutions(settings: Settings):
    return {
        "python": sys.executable,
        "powershell": shutil.which("powershell") or shutil.which("pwsh") or "powershell",
        "api_url": f"http://{settings.api_host}:{settings.api_port}",
    }


def expand(value: str, variables: dict[str, str]):
    # Replace only documented placeholders, preserving braces in other argv strings.
    return re.sub(r"\{(python|powershell|api_url)\}", lambda match: variables[match[1]], value)


def working_directory(value: str) -> Path:
    path = (REPO_ROOT / value).resolve()
    if not path.is_relative_to(REPO_ROOT) or not path.is_dir():
        raise LaunchError(f"Working directory must exist inside this project: {value}")
    return path


def readiness_url(value: str | None, variables):
    if value is None:
        return None
    url = expand(value, variables)
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        port = None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or not port
        or parsed.username
        or parsed.password
    ):
        raise LaunchError(
            "ready_url must be a local HTTP URL with an explicit port and no credentials."
        )
    return url


@contextmanager
def project_lock():
    directory = REPO_ROOT / "runtime/launcher"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "launcher.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise LaunchError(
                "This project already has a running launcher. Stop it before restarting."
            ) from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class Supervisor:
    def __init__(self, config: LaunchConfig, variables: dict[str, str], log_dir: Path):
        self.config, self.variables, self.log_dir = config, variables, log_dir
        self.running: dict[str, tuple[OwnedProcess, ServiceConfig]] = {}
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def spawn(self, name: str, spec: CommandConfig):
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        environment.setdefault("VIDEO_SERVICE_URL", self.variables["api_url"])
        child = OwnedProcess(
            [expand(part, self.variables) for part in spec.command],
            working_directory(spec.cwd),
            self.log_dir / f"{name}.log",
            environment,
        )
        print(f"[start] {name}; log: {child.log_path}", flush=True)
        return child

    def check_running(self):
        for name, (child, spec) in list(self.running.items()):
            code = child.poll()
            if code is not None:
                if spec.stop_project_on_exit:
                    raise LaunchError(f"{name} exited (code {code}); see {child.log_path}")
                print(f"[exit] {name} (code {code}); other services continue.", flush=True)
                child.close()
                del self.running[name]

    def wait_ready(self, name, child, spec):
        url = readiness_url(spec.ready_url, self.variables)
        deadline = time.monotonic() + spec.timeout_seconds
        with httpx.Client(trust_env=False, timeout=1) as client:
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise LaunchError(f"{name} failed to start; see {child.log_path}")
                self.check_running()
                if url is None:
                    time.sleep(0.3)
                    if child.poll() is not None:
                        raise LaunchError(f"{name} failed to start; see {child.log_path}")
                    print(f"[running] {name} (process started)", flush=True)
                    return
                try:
                    if client.get(url).status_code == 200:
                        print(f"[ready] {name}", flush=True)
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        raise LaunchError(f"{name} readiness timed out; see {child.log_path}")

    def preflight(self):
        ports = set()
        for name, spec in self.config.services.items():
            if spec.enabled and (url := readiness_url(spec.ready_url, self.variables)):
                port = urlsplit(url).port
                if port in ports:
                    raise LaunchError(f"Multiple services use port {port}.")
                ports.add(port)
                try:
                    with socket.socket() as probe:
                        if os.name == "nt":
                            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                        probe.bind(("127.0.0.1", port))
                except OSError:
                    raise LaunchError(
                        f"Port {port} for {name} is occupied. Stop that service or disable this entry; no existing process was stopped."
                    ) from None

    def run(self):
        self.preflight()
        try:
            for name, spec in self.config.prepare.items():
                if not spec.enabled:
                    continue
                child = self.spawn(f"prepare-{name}", spec)
                try:
                    deadline = time.monotonic() + spec.timeout_seconds
                    while child.poll() is None:
                        if time.monotonic() >= deadline:
                            raise LaunchError(f"Preparation {name} timed out; see {child.log_path}")
                        time.sleep(0.2)
                    if child.poll() != 0:
                        raise LaunchError(f"Preparation {name} failed; see {child.log_path}")
                    print(f"[done] {name}", flush=True)
                finally:
                    child.close()
            for name, spec in self.config.services.items():
                if spec.enabled:
                    child = self.spawn(name, spec)
                    self.running[name] = (child, spec)
                    self.wait_ready(name, child, spec)
            print(
                "Project started. Ctrl+C stops this launcher's processes; Docker data services stay running.",
                flush=True,
            )
            while self.running:
                self.check_running()
                time.sleep(0.3)
        finally:
            for child, _ in reversed(list(self.running.values())):
                child.close()
            self.running.clear()


def launch(config_path: str = "startup.yml", check: bool = False) -> int:
    try:
        path = (REPO_ROOT / config_path).resolve()
        config = load_config(path)
        variables = substitutions(Settings())
        # Validate disabled definitions too, so typos do not hide until a later enable.
        for spec in [*config.prepare.values(), *config.services.values()]:
            working_directory(spec.cwd)
        for spec in config.services.values():
            readiness_url(spec.ready_url, variables)
        print(f"Configuration: {path}", flush=True)
        for group in ("prepare", "services"):
            for name, spec in getattr(config, group).items():
                print(f"  {group}.{name}: {'enabled' if spec.enabled else 'disabled'}", flush=True)
        if check:
            print("Configuration valid; no commands executed.", flush=True)
            return 0
        previous = signal.getsignal(signal.SIGTERM)

        def interrupted(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, interrupted)
        try:
            with project_lock():
                directory = (
                    REPO_ROOT
                    / "runtime/launcher"
                    / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
                )
                Supervisor(config, variables, directory).run()
        finally:
            signal.signal(signal.SIGTERM, previous)
        return 0
    except KeyboardInterrupt:
        print("Stopped processes owned by this launcher.", flush=True)
        return 0
    except (LaunchError, OSError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr, flush=True)
        return 1
