"""Own subprocess trees, including Python launchers and PowerShell/pnpm descendants."""

import ctypes
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


class WindowsJob:
    def __init__(self):
        from ctypes import wintypes

        class Limits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", Limits),
                ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class OwnedProcess:
    def __init__(self, command: list[str], cwd: Path, log_path: Path, environment: dict[str, str]):
        self.log_path = log_path
        self.job = WindowsJob() if os.name == "nt" else None
        self.process = None
        self.log = log_path.open("ab", buffering=0)
        # The base interpreter runs only stdlib bootstrap code. It does not create the
        # extra venv launcher process before job assignment, avoiding an ownership race.
        bootstrap = Path(__file__).resolve().parents[1] / "_launch_child.py"
        try:
            self.process = subprocess.Popen(
                [getattr(sys, "_base_executable", sys.executable), "-u", str(bootstrap)],
                cwd=cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=self.log,
                stderr=self.log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
            if self.job:
                self.job.assign(self.process)
            self.process.stdin.write((json.dumps(command) + "\n").encode())
            self.process.stdin.close()
        except BaseException:
            self.close()
            raise

    def poll(self):
        return self.process.poll()

    def close(self):
        if self.job:
            self.job.close()
        elif self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if self.process:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            if self.process.poll() is None:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        os.killpg(self.process.pid, signal.SIGKILL)
                    else:
                        self.process.kill()
                    self.process.wait(timeout=3)
        self.log.close()
