"""Standard-library bootstrap: wait for process ownership before starting any descendants."""

import json
import subprocess
import sys

if __name__ == "__main__":
    try:
        command = json.loads(sys.stdin.readline())
        result = subprocess.run(command, stdin=subprocess.DEVNULL, check=False)
        raise SystemExit(result.returncode)
    except (OSError, ValueError) as exc:
        print(f"Unable to start configured command: {type(exc).__name__}", flush=True)
        raise SystemExit(1) from None
