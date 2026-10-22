"""Run the shipped frontend's receipt checks without browser packages."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_does_not_repeat_ambiguous_commands_and_recovers_owner_receipts():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable; frontend command checks need its standard library")
    subprocess.run(
        [node, str(Path(__file__).with_name("browser_command_checks.cjs"))],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
