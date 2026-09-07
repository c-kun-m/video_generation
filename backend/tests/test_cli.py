import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from video_generation import cli
from video_generation.config import REPO_ROOT


@pytest.mark.parametrize(
    "target",
    [["-m", "video_generation"], ["-m", "video_generation.cli"], [str(Path(cli.__file__))]],
)
@pytest.mark.parametrize("directory", [REPO_ROOT, REPO_ROOT / "backend"])
def test_installed_cli_help_from_each_supported_directory(target, directory):
    result = subprocess.run(
        [sys.executable, *target, "--help"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "serve" in result.stdout and "init-owner" in result.stdout


def test_cli_serve_keeps_the_supported_server_entrypoint():
    with patch.object(cli, "serve") as serve:
        cli.main(["serve"])
    serve.assert_called_once_with()


def test_cli_without_command_does_not_start_server_or_issue_credentials():
    with patch.object(cli, "serve") as serve, patch.object(cli, "_pair") as pair:
        with pytest.raises(SystemExit) as result:
            cli.main([])
    assert result.value.code == 2
    serve.assert_not_called()
    pair.assert_not_called()
